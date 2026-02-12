"""Tests for Pattern Currency health check.

Run with: .venv/bin/pytest tests/test_health_pattern_currency.py --no-cov -v
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from reos.cairn.health.checks.pattern_currency import PatternCurrencyCheck
from reos.cairn.health.runner import Severity
from reos.db import Database


@pytest.fixture
def db(tmp_path: Path) -> Database:
    """Create a test database with atomic_operations schema."""
    db_path = tmp_path / "test_reos.db"
    database = Database(db_path)
    conn = database.connect()

    # Create atomic_operations table
    conn.execute("""
        CREATE TABLE atomic_operations (
            id TEXT PRIMARY KEY,
            user_request TEXT NOT NULL,
            destination_type TEXT,
            consumer_type TEXT,
            execution_semantics TEXT,
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()

    return database


def test_insufficient_data_baseline_returns_healthy(db: Database):
    """With fewer than MINIMUM_OPERATIONS in baseline window, check returns healthy."""
    check = PatternCurrencyCheck(db)

    # Insert 15 operations in baseline (need 20+)
    now = datetime.now()
    baseline_start = now - timedelta(days=40)

    conn = db.connect()
    for i in range(15):
        timestamp = (baseline_start + timedelta(hours=i)).isoformat()
        conn.execute(
            """
            INSERT INTO atomic_operations
            (id, user_request, destination_type, consumer_type, execution_semantics, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (f"op-{i}", f"test request {i}", "stream", "human", "read", timestamp),
        )
    conn.commit()

    results = check.run()

    assert len(results) == 1
    assert results[0].severity == Severity.HEALTHY
    assert "Not enough data" in results[0].title
    assert "Baseline: 15 ops" in results[0].details
    assert results[0].finding_key == "pattern_currency:insufficient_data"


def test_insufficient_data_recent_returns_healthy(db: Database):
    """With fewer than MINIMUM_OPERATIONS in recent window, check returns healthy."""
    check = PatternCurrencyCheck(db)

    # Insert 30 operations in baseline (enough), but only 10 in recent
    now = datetime.now()
    baseline_start = now - timedelta(days=50)

    conn = db.connect()
    for i in range(30):
        timestamp = (baseline_start + timedelta(hours=i)).isoformat()
        conn.execute(
            """
            INSERT INTO atomic_operations
            (id, user_request, destination_type, consumer_type, execution_semantics, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (f"op-baseline-{i}", f"baseline request {i}", "stream", "human", "read", timestamp),
        )

    # Add 10 recent operations (need 20+)
    recent_start = now - timedelta(days=3)
    for i in range(10):
        timestamp = (recent_start + timedelta(hours=i)).isoformat()
        conn.execute(
            """
            INSERT INTO atomic_operations
            (id, user_request, destination_type, consumer_type, execution_semantics, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (f"op-recent-{i}", f"recent request {i}", "stream", "human", "read", timestamp),
        )
    conn.commit()

    results = check.run()

    assert len(results) == 1
    assert results[0].severity == Severity.HEALTHY
    assert "Not enough data" in results[0].title
    assert "Recent: 10 ops" in results[0].details


def test_identical_distributions_returns_healthy(db: Database):
    """When baseline and recent distributions are identical, check returns healthy."""
    check = PatternCurrencyCheck(db)

    now = datetime.now()
    baseline_start = now - timedelta(days=50)
    recent_start = now - timedelta(days=5)

    conn = db.connect()

    # Insert 25 ops in baseline: 20 stream/human/read, 5 file/human/execute
    for i in range(20):
        timestamp = (baseline_start + timedelta(hours=i)).isoformat()
        conn.execute(
            """
            INSERT INTO atomic_operations
            (id, user_request, destination_type, consumer_type, execution_semantics, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (f"op-baseline-{i}", f"request {i}", "stream", "human", "read", timestamp),
        )
    for i in range(5):
        timestamp = (baseline_start + timedelta(hours=20 + i)).isoformat()
        conn.execute(
            """
            INSERT INTO atomic_operations
            (id, user_request, destination_type, consumer_type, execution_semantics, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (f"op-baseline-file-{i}", f"file request {i}", "file", "human", "execute", timestamp),
        )

    # Insert 25 recent ops with same distribution
    for i in range(20):
        timestamp = (recent_start + timedelta(hours=i)).isoformat()
        conn.execute(
            """
            INSERT INTO atomic_operations
            (id, user_request, destination_type, consumer_type, execution_semantics, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (f"op-recent-{i}", f"recent request {i}", "stream", "human", "read", timestamp),
        )
    for i in range(5):
        timestamp = (recent_start + timedelta(hours=20 + i)).isoformat()
        conn.execute(
            """
            INSERT INTO atomic_operations
            (id, user_request, destination_type, consumer_type, execution_semantics, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                f"op-recent-file-{i}",
                f"recent file request {i}",
                "file",
                "human",
                "execute",
                timestamp,
            ),
        )
    conn.commit()

    results = check.run()

    assert len(results) == 1
    assert results[0].severity == Severity.HEALTHY
    assert "Classification patterns stable" in results[0].title
    assert results[0].finding_key == "pattern_currency:ok"


def test_small_drift_below_threshold_returns_healthy(db: Database):
    """Small drift below 15% warning threshold returns healthy."""
    check = PatternCurrencyCheck(db)

    now = datetime.now()
    baseline_start = now - timedelta(days=50)
    recent_start = now - timedelta(days=5)

    conn = db.connect()

    # Baseline: 100% stream/human/read (25 ops)
    for i in range(25):
        timestamp = (baseline_start + timedelta(hours=i)).isoformat()
        conn.execute(
            """
            INSERT INTO atomic_operations
            (id, user_request, destination_type, consumer_type, execution_semantics, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (f"op-baseline-{i}", f"request {i}", "stream", "human", "read", timestamp),
        )

    # Recent: 90% stream/human/read (18 ops), 10% file/human/execute (2 ops)
    # Total: 20 ops
    for i in range(18):
        timestamp = (recent_start + timedelta(hours=i)).isoformat()
        conn.execute(
            """
            INSERT INTO atomic_operations
            (id, user_request, destination_type, consumer_type, execution_semantics, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (f"op-recent-{i}", f"recent request {i}", "stream", "human", "read", timestamp),
        )
    for i in range(2):
        timestamp = (recent_start + timedelta(hours=18 + i)).isoformat()
        conn.execute(
            """
            INSERT INTO atomic_operations
            (id, user_request, destination_type, consumer_type, execution_semantics, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                f"op-recent-file-{i}",
                f"recent file request {i}",
                "file",
                "human",
                "execute",
                timestamp,
            ),
        )
    conn.commit()

    results = check.run()

    # TVD = 0.5 * (|1.0 - 0.9| + |0 - 0.1|) = 0.5 * 0.2 = 0.1 (10%, below 15%)
    assert len(results) == 1
    assert results[0].severity == Severity.HEALTHY
    assert "Classification patterns stable" in results[0].title


def test_medium_drift_15_to_30_percent_returns_warning(db: Database):
    """Drift between 15-30% returns warning severity."""
    check = PatternCurrencyCheck(db)

    now = datetime.now()
    baseline_start = now - timedelta(days=50)
    recent_start = now - timedelta(days=5)

    conn = db.connect()

    # Baseline: 100% stream/human/read (25 ops)
    for i in range(25):
        timestamp = (baseline_start + timedelta(hours=i)).isoformat()
        conn.execute(
            """
            INSERT INTO atomic_operations
            (id, user_request, destination_type, consumer_type, execution_semantics, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (f"op-baseline-{i}", f"request {i}", "stream", "human", "read", timestamp),
        )

    # Recent: 75% stream/human/read (15 ops), 25% file/human/execute (5 ops)
    # Total: 20 ops
    for i in range(15):
        timestamp = (recent_start + timedelta(hours=i)).isoformat()
        conn.execute(
            """
            INSERT INTO atomic_operations
            (id, user_request, destination_type, consumer_type, execution_semantics, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (f"op-recent-{i}", f"recent request {i}", "stream", "human", "read", timestamp),
        )
    for i in range(5):
        timestamp = (recent_start + timedelta(hours=15 + i)).isoformat()
        conn.execute(
            """
            INSERT INTO atomic_operations
            (id, user_request, destination_type, consumer_type, execution_semantics, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                f"op-recent-file-{i}",
                f"recent file request {i}",
                "file",
                "human",
                "execute",
                timestamp,
            ),
        )
    conn.commit()

    results = check.run()

    # TVD = 0.5 * (|1.0 - 0.75| + |0 - 0.25|) = 0.5 * 0.5 = 0.25 (25%, warning range)
    assert len(results) == 1
    assert results[0].severity == Severity.WARNING
    assert "Mild classification drift detected" in results[0].title
    # Should show percentage in title
    assert "%" in results[0].title
    assert "distribution of classification types has shifted slightly" in results[0].details


def test_large_drift_above_30_percent_returns_critical(db: Database):
    """Drift above 30% returns critical severity."""
    check = PatternCurrencyCheck(db)

    now = datetime.now()
    baseline_start = now - timedelta(days=50)
    recent_start = now - timedelta(days=5)

    conn = db.connect()

    # Baseline: 100% stream/human/read (25 ops)
    for i in range(25):
        timestamp = (baseline_start + timedelta(hours=i)).isoformat()
        conn.execute(
            """
            INSERT INTO atomic_operations
            (id, user_request, destination_type, consumer_type, execution_semantics, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (f"op-baseline-{i}", f"request {i}", "stream", "human", "read", timestamp),
        )

    # Recent: 50% stream/human/read (10 ops), 50% process/machine/execute (10 ops)
    # Total: 20 ops
    for i in range(10):
        timestamp = (recent_start + timedelta(hours=i)).isoformat()
        conn.execute(
            """
            INSERT INTO atomic_operations
            (id, user_request, destination_type, consumer_type, execution_semantics, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (f"op-recent-{i}", f"recent request {i}", "stream", "human", "read", timestamp),
        )
    for i in range(10):
        timestamp = (recent_start + timedelta(hours=10 + i)).isoformat()
        conn.execute(
            """
            INSERT INTO atomic_operations
            (id, user_request, destination_type, consumer_type, execution_semantics, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                f"op-recent-proc-{i}",
                f"recent process {i}",
                "process",
                "machine",
                "execute",
                timestamp,
            ),
        )
    conn.commit()

    results = check.run()

    # TVD = 0.5 * (|1.0 - 0.5| + |0 - 0.5|) = 0.5 * 1.0 = 0.5 (50%, above 30%)
    assert len(results) == 1
    assert results[0].severity == Severity.CRITICAL
    assert "Significant classification drift detected" in results[0].title
    assert "%" in results[0].title
    assert "shifted significantly" in results[0].details
    assert "model update" in results[0].details


def test_total_variation_distance_identical_distributions():
    """TVD of identical distributions should be 0.0."""
    dist1 = {"a": 10, "b": 20, "c": 30}
    dist2 = {"a": 10, "b": 20, "c": 30}

    tvd = PatternCurrencyCheck._total_variation_distance(dist1, dist2)

    assert tvd == 0.0


def test_total_variation_distance_completely_disjoint():
    """TVD of completely disjoint distributions should be 1.0."""
    dist1 = {"a": 100}
    dist2 = {"b": 100}

    tvd = PatternCurrencyCheck._total_variation_distance(dist1, dist2)

    assert tvd == 1.0


def test_total_variation_distance_partial_overlap():
    """TVD of partially overlapping distributions should be intermediate."""
    # dist1: 50% a, 50% b
    # dist2: 75% a, 25% c
    # TVD = 0.5 * (|0.5 - 0.75| + |0.5 - 0| + |0 - 0.25|) = 0.5 * 1.0 = 0.5
    dist1 = {"a": 50, "b": 50}
    dist2 = {"a": 75, "c": 25}

    tvd = PatternCurrencyCheck._total_variation_distance(dist1, dist2)

    assert tvd == 0.5


def test_total_variation_distance_handles_empty_distributions():
    """TVD with empty distribution should handle gracefully."""
    dist1 = {"a": 10}
    dist2 = {}

    tvd = PatternCurrencyCheck._total_variation_distance(dist1, dist2)

    # dist1 normalized: a=1.0
    # dist2 normalized: (empty, so all keys treated as 0)
    # TVD = 0.5 * |1.0 - 0| = 0.5
    assert tvd == 0.5


def test_database_error_returns_healthy_gracefully(tmp_path: Path):
    """Database connection failure returns healthy result gracefully."""

    class FailingDatabase:
        def connect(self):
            raise sqlite3.OperationalError("Database locked")

    check = PatternCurrencyCheck(FailingDatabase())
    results = check.run()

    assert len(results) == 1
    assert results[0].severity == Severity.HEALTHY
    assert "Classification history not yet available" in results[0].title
    assert results[0].finding_key == "pattern_currency:unavailable"


def test_finding_key_includes_tvd_for_drift(db: Database):
    """Finding key should include TVD value for drift events."""
    check = PatternCurrencyCheck(db)

    now = datetime.now()
    baseline_start = now - timedelta(days=50)
    recent_start = now - timedelta(days=5)

    conn = db.connect()

    # Create a warning-level drift (20% TVD)
    # Baseline: 100% stream/human/read (25 ops)
    for i in range(25):
        timestamp = (baseline_start + timedelta(hours=i)).isoformat()
        conn.execute(
            """
            INSERT INTO atomic_operations
            (id, user_request, destination_type, consumer_type, execution_semantics, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (f"op-baseline-{i}", f"request {i}", "stream", "human", "read", timestamp),
        )

    # Recent: 80% stream/human/read (16 ops), 20% file/human/execute (4 ops)
    for i in range(16):
        timestamp = (recent_start + timedelta(hours=i)).isoformat()
        conn.execute(
            """
            INSERT INTO atomic_operations
            (id, user_request, destination_type, consumer_type, execution_semantics, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (f"op-recent-{i}", f"recent request {i}", "stream", "human", "read", timestamp),
        )
    for i in range(4):
        timestamp = (recent_start + timedelta(hours=16 + i)).isoformat()
        conn.execute(
            """
            INSERT INTO atomic_operations
            (id, user_request, destination_type, consumer_type, execution_semantics, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (f"op-recent-file-{i}", f"file request {i}", "file", "human", "execute", timestamp),
        )
    conn.commit()

    results = check.run()

    # TVD = 0.5 * (|1.0 - 0.8| + |0 - 0.2|) = 0.5 * 0.4 = 0.2
    assert results[0].severity == Severity.WARNING
    # Finding key should include TVD value for deduplication
    assert results[0].finding_key.startswith("pattern_currency:warning:")
    assert "0.20" in results[0].finding_key
