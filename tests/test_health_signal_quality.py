"""Tests for Signal Quality health check.

Run with: PYTHONPATH=src pytest tests/test_health_signal_quality.py -v --no-cov
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from reos.atomic_ops.schema import init_atomic_ops_schema
from reos.cairn.health.checks.signal_quality import SignalQualityCheck
from reos.cairn.health.runner import Severity


@pytest.fixture
def db_with_feedback(tmp_path: Path):
    """Create a Database-like object with user_feedback table."""
    db_path = tmp_path / "reos.db"

    # Create a mock Database object that returns a real connection
    mock_db = MagicMock()

    def connect():
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        init_atomic_ops_schema(conn)
        return conn

    mock_db.connect = connect
    return mock_db


def test_no_feedback_returns_healthy(db_with_feedback):
    """With no feedback data, check should return healthy (insufficient data)."""
    check = SignalQualityCheck(db_with_feedback)
    results = check.run()

    assert len(results) == 1
    assert results[0].severity == Severity.HEALTHY
    assert "0 approvals" in results[0].title
    assert "Not enough data yet" in results[0].title
    assert results[0].finding_key == "signal_quality:insufficient_data"


def test_insufficient_feedback_returns_healthy(db_with_feedback):
    """With <10 feedback entries, check should return healthy."""
    conn = db_with_feedback.connect()

    # Create an operation first
    conn.execute(
        """
        INSERT INTO atomic_operations (
            id, user_request, user_id, status, created_at
        ) VALUES ('op-1', 'test request', 'local', 'complete', datetime('now'))
        """
    )

    # Create 5 approval feedbacks (below threshold)
    for i in range(5):
        conn.execute(
            """
            INSERT INTO user_feedback (
                id, operation_id, user_id, feedback_type,
                approved, time_to_decision_ms, created_at
            ) VALUES (?, 'op-1', 'local', 'approval', 1, 2000, datetime('now'))
            """,
            (f"fb-{i}",),
        )
    conn.commit()
    conn.close()

    check = SignalQualityCheck(db_with_feedback)
    results = check.run()

    assert len(results) == 1
    assert results[0].severity == Severity.HEALTHY
    assert "5 approvals" in results[0].title
    assert "Not enough data yet" in results[0].title
    assert results[0].finding_key == "signal_quality:insufficient_data"


def test_deliberate_reviews_return_healthy(db_with_feedback):
    """When most approvals are >1s, check should return healthy."""
    conn = db_with_feedback.connect()

    conn.execute(
        """
        INSERT INTO atomic_operations (
            id, user_request, user_id, status, created_at
        ) VALUES ('op-1', 'test request', 'local', 'complete', datetime('now'))
        """
    )

    # Create 20 approval feedbacks with mostly deliberate times
    for i in range(20):
        # 3 rapid (<1s), 17 deliberate (>1s) = 15% rapid
        time_ms = 500 if i < 3 else 2000
        conn.execute(
            """
            INSERT INTO user_feedback (
                id, operation_id, user_id, feedback_type,
                approved, time_to_decision_ms, created_at
            ) VALUES (?, 'op-1', 'local', 'approval', 1, ?, datetime('now'))
            """,
            (f"fb-{i}", time_ms),
        )
    conn.commit()
    conn.close()

    check = SignalQualityCheck(db_with_feedback)
    results = check.run()

    assert len(results) == 1
    assert results[0].severity == Severity.HEALTHY
    assert "deliberate" in results[0].title.lower()
    assert results[0].finding_key == "signal_quality:ok"


def test_high_rapid_proportion_returns_warning(db_with_feedback):
    """When >50% of approvals are <1s, check should return warning."""
    conn = db_with_feedback.connect()

    conn.execute(
        """
        INSERT INTO atomic_operations (
            id, user_request, user_id, status, created_at
        ) VALUES ('op-1', 'test request', 'local', 'complete', datetime('now'))
        """
    )

    # Create 20 approval feedbacks with 12 rapid (60%)
    for i in range(20):
        time_ms = 500 if i < 12 else 2000
        conn.execute(
            """
            INSERT INTO user_feedback (
                id, operation_id, user_id, feedback_type,
                approved, time_to_decision_ms, created_at
            ) VALUES (?, 'op-1', 'local', 'approval', 1, ?, datetime('now'))
            """,
            (f"fb-{i}", time_ms),
        )
    conn.commit()
    conn.close()

    check = SignalQualityCheck(db_with_feedback)
    results = check.run()

    assert len(results) == 1
    assert results[0].severity == Severity.WARNING
    assert "60%" in results[0].title
    assert "very quick (<1s)" in results[0].title
    assert "12 of 20" in results[0].details
    assert "less than 1 second" in results[0].details
    assert "may not be giving enough time" in results[0].details
    assert "signal_quality:rapid:0.60" == results[0].finding_key


def test_exactly_at_threshold_returns_warning(db_with_feedback):
    """Exactly 50% rapid approvals should trigger warning."""
    conn = db_with_feedback.connect()

    conn.execute(
        """
        INSERT INTO atomic_operations (
            id, user_request, user_id, status, created_at
        ) VALUES ('op-1', 'test request', 'local', 'complete', datetime('now'))
        """
    )

    # Create 20 approval feedbacks with exactly 10 rapid (50%)
    for i in range(20):
        time_ms = 999 if i < 10 else 1000
        conn.execute(
            """
            INSERT INTO user_feedback (
                id, operation_id, user_id, feedback_type,
                approved, time_to_decision_ms, created_at
            ) VALUES (?, 'op-1', 'local', 'approval', 1, ?, datetime('now'))
            """,
            (f"fb-{i}", time_ms),
        )
    conn.commit()
    conn.close()

    check = SignalQualityCheck(db_with_feedback)
    results = check.run()

    assert len(results) == 1
    assert results[0].severity == Severity.WARNING
    assert "50%" in results[0].title


def test_exactly_999ms_counts_as_rapid(db_with_feedback):
    """999ms should count as rapid (<1000ms threshold)."""
    conn = db_with_feedback.connect()

    conn.execute(
        """
        INSERT INTO atomic_operations (
            id, user_request, user_id, status, created_at
        ) VALUES ('op-1', 'test request', 'local', 'complete', datetime('now'))
        """
    )

    # All approvals at 999ms (just under threshold)
    for i in range(20):
        conn.execute(
            """
            INSERT INTO user_feedback (
                id, operation_id, user_id, feedback_type,
                approved, time_to_decision_ms, created_at
            ) VALUES (?, 'op-1', 'local', 'approval', 1, 999, datetime('now'))
            """,
            (f"fb-{i}",),
        )
    conn.commit()
    conn.close()

    check = SignalQualityCheck(db_with_feedback)
    results = check.run()

    assert len(results) == 1
    assert results[0].severity == Severity.WARNING
    assert "100%" in results[0].title


def test_exactly_1000ms_not_rapid(db_with_feedback):
    """1000ms should NOT count as rapid (threshold is <1000ms)."""
    conn = db_with_feedback.connect()

    conn.execute(
        """
        INSERT INTO atomic_operations (
            id, user_request, user_id, status, created_at
        ) VALUES ('op-1', 'test request', 'local', 'complete', datetime('now'))
        """
    )

    # All approvals at exactly 1000ms (at threshold)
    for i in range(20):
        conn.execute(
            """
            INSERT INTO user_feedback (
                id, operation_id, user_id, feedback_type,
                approved, time_to_decision_ms, created_at
            ) VALUES (?, 'op-1', 'local', 'approval', 1, 1000, datetime('now'))
            """,
            (f"fb-{i}",),
        )
    conn.commit()
    conn.close()

    check = SignalQualityCheck(db_with_feedback)
    results = check.run()

    assert len(results) == 1
    assert results[0].severity == Severity.HEALTHY
    assert "deliberate" in results[0].title.lower()


def test_ignores_null_time_to_decision(db_with_feedback):
    """Feedback entries with NULL time_to_decision_ms should be ignored."""
    conn = db_with_feedback.connect()

    conn.execute(
        """
        INSERT INTO atomic_operations (
            id, user_request, user_id, status, created_at
        ) VALUES ('op-1', 'test request', 'local', 'complete', datetime('now'))
        """
    )

    # Create 15 entries with NULL times (should be ignored)
    for i in range(15):
        conn.execute(
            """
            INSERT INTO user_feedback (
                id, operation_id, user_id, feedback_type,
                approved, time_to_decision_ms, created_at
            ) VALUES (?, 'op-1', 'local', 'approval', 1, NULL, datetime('now'))
            """,
            (f"fb-null-{i}",),
        )

    # Create 5 entries with valid times (below minimum)
    for i in range(5):
        conn.execute(
            """
            INSERT INTO user_feedback (
                id, operation_id, user_id, feedback_type,
                approved, time_to_decision_ms, created_at
            ) VALUES (?, 'op-1', 'local', 'approval', 1, 2000, datetime('now'))
            """,
            (f"fb-valid-{i}",),
        )

    conn.commit()
    conn.close()

    check = SignalQualityCheck(db_with_feedback)
    results = check.run()

    # Should see insufficient data (only 5 valid entries)
    assert len(results) == 1
    assert results[0].severity == Severity.HEALTHY
    assert "5 approvals" in results[0].title


def test_only_checks_approval_feedback(db_with_feedback):
    """Only approval feedback should be checked, not corrections."""
    conn = db_with_feedback.connect()

    conn.execute(
        """
        INSERT INTO atomic_operations (
            id, user_request, user_id, status, created_at
        ) VALUES ('op-1', 'test request', 'local', 'complete', datetime('now'))
        """
    )

    # Create 10 correction feedbacks (should be ignored)
    for i in range(10):
        conn.execute(
            """
            INSERT INTO user_feedback (
                id, operation_id, user_id, feedback_type,
                system_classification, user_corrected_destination,
                time_to_decision_ms, created_at
            ) VALUES (?, 'op-1', 'local', 'correction', '{}', 'file', 500, datetime('now'))
            """,
            (f"fb-corr-{i}",),
        )

    # Create 5 approval feedbacks (below minimum)
    for i in range(5):
        conn.execute(
            """
            INSERT INTO user_feedback (
                id, operation_id, user_id, feedback_type,
                approved, time_to_decision_ms, created_at
            ) VALUES (?, 'op-1', 'local', 'approval', 1, 2000, datetime('now'))
            """,
            (f"fb-appr-{i}",),
        )

    conn.commit()
    conn.close()

    check = SignalQualityCheck(db_with_feedback)
    results = check.run()

    # Should only see 5 approvals, not the 10 corrections
    assert len(results) == 1
    assert results[0].severity == Severity.HEALTHY
    assert "5 approvals" in results[0].title
