"""Tests for health snapshot functions.

Run with: .venv/bin/pytest tests/test_health_snapshot.py --no-cov -v
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from pathlib import Path

import pytest

from cairn.cairn.health.snapshot import (
    create_daily_snapshot,
    get_snapshots,
    init_snapshot_tables,
    log_drift_event,
)


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    """Create a test database connection."""
    db_path = tmp_path / "test_cairn.db"
    connection = sqlite3.connect(str(db_path))
    return connection


def test_init_snapshot_tables_creates_tables_without_error(conn: sqlite3.Connection):
    """init_snapshot_tables should create tables successfully."""
    init_snapshot_tables(conn)

    # Verify health_snapshots table exists
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='health_snapshots'"
    )
    assert cursor.fetchone() is not None

    # Verify pattern_drift_events table exists
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='pattern_drift_events'"
    )
    assert cursor.fetchone() is not None


def test_init_snapshot_tables_idempotent(conn: sqlite3.Connection):
    """init_snapshot_tables can be called multiple times safely."""
    init_snapshot_tables(conn)
    init_snapshot_tables(conn)  # Should not error

    # Tables should still exist
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='health_snapshots'"
    )
    assert cursor.fetchone() is not None


def test_create_daily_snapshot_creates_snapshot_for_today(conn: sqlite3.Connection):
    """create_daily_snapshot should insert a snapshot record."""
    init_snapshot_tables(conn)

    metrics = {
        "stale_acts_count": 2,
        "classification_drift_tvd": 0.15,
        "recent_operations": 45,
    }

    result = create_daily_snapshot(conn, metrics)

    assert result is True

    # Verify snapshot was created
    today = date.today().isoformat()
    cursor = conn.execute(
        "SELECT snapshot_date, metrics_json FROM health_snapshots WHERE snapshot_date = ?",
        (today,),
    )
    row = cursor.fetchone()
    assert row is not None
    assert row[0] == today

    stored_metrics = json.loads(row[1])
    assert stored_metrics == metrics


def test_create_daily_snapshot_returns_false_if_exists(conn: sqlite3.Connection):
    """create_daily_snapshot should return False if today's snapshot already exists."""
    init_snapshot_tables(conn)

    metrics = {"value": 1}

    # Create first snapshot
    result1 = create_daily_snapshot(conn, metrics)
    assert result1 is True

    # Try to create second snapshot for same day
    result2 = create_daily_snapshot(conn, metrics)
    assert result2 is False

    # Verify only one snapshot exists
    today = date.today().isoformat()
    cursor = conn.execute(
        "SELECT COUNT(*) FROM health_snapshots WHERE snapshot_date = ?",
        (today,),
    )
    count = cursor.fetchone()[0]
    assert count == 1


def test_get_snapshots_returns_snapshots_in_chronological_order(conn: sqlite3.Connection):
    """get_snapshots should return snapshots ordered by date ascending."""
    init_snapshot_tables(conn)

    # Insert snapshots for different dates (out of order)
    snapshots_data = [
        ("2026-01-15", {"value": 1}, "2026-01-15T08:00:00"),
        ("2026-01-10", {"value": 2}, "2026-01-10T08:00:00"),
        ("2026-01-20", {"value": 3}, "2026-01-20T08:00:00"),
    ]

    for snapshot_date, metrics, created_at in snapshots_data:
        conn.execute(
            """
            INSERT INTO health_snapshots (snapshot_date, metrics_json, created_at)
            VALUES (?, ?, ?)
            """,
            (snapshot_date, json.dumps(metrics), created_at),
        )
    conn.commit()

    results = get_snapshots(conn)

    # Should be ordered by date ascending
    assert len(results) == 3
    assert results[0]["date"] == "2026-01-10"
    assert results[0]["metrics"]["value"] == 2
    assert results[1]["date"] == "2026-01-15"
    assert results[1]["metrics"]["value"] == 1
    assert results[2]["date"] == "2026-01-20"
    assert results[2]["metrics"]["value"] == 3


def test_get_snapshots_respects_days_limit(conn: sqlite3.Connection):
    """get_snapshots should limit results to specified number of days."""
    init_snapshot_tables(conn)

    # Insert 5 snapshots
    for i in range(5):
        snapshot_date = f"2026-01-{10+i:02d}"
        conn.execute(
            """
            INSERT INTO health_snapshots (snapshot_date, metrics_json, created_at)
            VALUES (?, ?, ?)
            """,
            (snapshot_date, json.dumps({"index": i}), snapshot_date + "T08:00:00"),
        )
    conn.commit()

    # Request only 3 most recent
    results = get_snapshots(conn, days=3)

    # Should return 3 most recent, in chronological order
    assert len(results) == 3
    assert results[0]["date"] == "2026-01-12"  # 3rd oldest overall
    assert results[1]["date"] == "2026-01-13"
    assert results[2]["date"] == "2026-01-14"  # Most recent


def test_get_snapshots_handles_malformed_json_gracefully(conn: sqlite3.Connection):
    """get_snapshots should handle malformed JSON without crashing."""
    init_snapshot_tables(conn)

    # Insert snapshot with valid JSON
    conn.execute(
        """
        INSERT INTO health_snapshots (snapshot_date, metrics_json, created_at)
        VALUES (?, ?, ?)
        """,
        ("2026-01-10", json.dumps({"value": 1}), "2026-01-10T08:00:00"),
    )

    # Insert snapshot with malformed JSON
    conn.execute(
        """
        INSERT INTO health_snapshots (snapshot_date, metrics_json, created_at)
        VALUES (?, ?, ?)
        """,
        ("2026-01-11", "invalid json {", "2026-01-11T08:00:00"),
    )

    conn.commit()

    results = get_snapshots(conn)

    # Should return both, with malformed one having empty metrics
    assert len(results) == 2
    assert results[0]["metrics"] == {"value": 1}
    assert results[1]["metrics"] == {}  # Malformed JSON becomes empty dict


def test_log_drift_event_stores_event_correctly(conn: sqlite3.Connection):
    """log_drift_event should insert drift event with all fields."""
    init_snapshot_tables(conn)

    details = {
        "baseline_distribution": {"stream/human/read": 100},
        "recent_distribution": {"stream/human/read": 60, "file/human/execute": 40},
    }

    log_drift_event(
        conn,
        event_id="drift-2026-01-15",
        drift_magnitude=0.4,
        baseline_days=60,
        recent_days=7,
        details=details,
    )

    # Verify event was stored
    cursor = conn.execute(
        """
        SELECT event_id, drift_magnitude, baseline_window_days,
               recent_window_days, details_json, detected_at
        FROM pattern_drift_events
        WHERE event_id = ?
        """,
        ("drift-2026-01-15",),
    )
    row = cursor.fetchone()

    assert row is not None
    assert row[0] == "drift-2026-01-15"
    assert row[1] == 0.4
    assert row[2] == 60
    assert row[3] == 7

    stored_details = json.loads(row[4])
    assert stored_details == details

    # Verify detected_at is a valid ISO timestamp
    detected_at = row[5]
    datetime.fromisoformat(detected_at)  # Should not raise


def test_log_drift_event_with_none_details(conn: sqlite3.Connection):
    """log_drift_event should handle None details gracefully."""
    init_snapshot_tables(conn)

    log_drift_event(
        conn,
        event_id="drift-no-details",
        drift_magnitude=0.25,
        baseline_days=60,
        recent_days=7,
        details=None,
    )

    # Verify event was stored with NULL details
    cursor = conn.execute(
        "SELECT details_json FROM pattern_drift_events WHERE event_id = ?",
        ("drift-no-details",),
    )
    row = cursor.fetchone()

    assert row is not None
    assert row[0] is None


def test_snapshot_created_at_is_iso_timestamp(conn: sqlite3.Connection):
    """Snapshot created_at field should be valid ISO timestamp."""
    init_snapshot_tables(conn)

    metrics = {"test": 123}
    create_daily_snapshot(conn, metrics)

    today = date.today().isoformat()
    cursor = conn.execute(
        "SELECT created_at FROM health_snapshots WHERE snapshot_date = ?",
        (today,),
    )
    row = cursor.fetchone()

    # Should parse without error
    created_at = datetime.fromisoformat(row[0])
    assert isinstance(created_at, datetime)


def test_get_snapshots_includes_created_at(conn: sqlite3.Connection):
    """get_snapshots results should include created_at field."""
    init_snapshot_tables(conn)

    metrics = {"value": 42}
    create_daily_snapshot(conn, metrics)

    results = get_snapshots(conn)

    assert len(results) == 1
    assert "created_at" in results[0]
    # Verify it's a valid timestamp
    datetime.fromisoformat(results[0]["created_at"])


def test_get_snapshots_with_zero_days_limit(conn: sqlite3.Connection):
    """get_snapshots with days=0 should handle gracefully."""
    init_snapshot_tables(conn)

    # Insert a snapshot
    conn.execute(
        """
        INSERT INTO health_snapshots (snapshot_date, metrics_json, created_at)
        VALUES (?, ?, ?)
        """,
        ("2026-01-10", json.dumps({"value": 1}), "2026-01-10T08:00:00"),
    )
    conn.commit()

    results = get_snapshots(conn, days=0)

    # SQLite LIMIT 0 returns no rows
    assert len(results) == 0


def test_log_drift_event_with_empty_details_dict(conn: sqlite3.Connection):
    """log_drift_event should handle empty dict details."""
    init_snapshot_tables(conn)

    log_drift_event(
        conn,
        event_id="drift-empty-details",
        drift_magnitude=0.18,
        baseline_days=60,
        recent_days=7,
        details={},
    )

    cursor = conn.execute(
        "SELECT details_json FROM pattern_drift_events WHERE event_id = ?",
        ("drift-empty-details",),
    )
    row = cursor.fetchone()

    assert row is not None
    # Empty dict is falsy in Python, so the expression becomes None
    assert row[0] is None
