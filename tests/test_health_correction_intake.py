"""Tests for Correction Intake health check.

Run with: PYTHONPATH=src pytest tests/test_health_correction_intake.py -v --no-cov
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from reos.atomic_ops.schema import init_atomic_ops_schema
from reos.cairn.health.checks.correction_intake import CorrectionIntakeCheck
from reos.cairn.health.runner import Severity


@pytest.fixture
def db_with_atomic_ops(tmp_path: Path):
    """Create a Database-like object with atomic_ops schema."""
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


def test_no_data_returns_healthy(db_with_atomic_ops):
    """With no atomic operations, check should return healthy (insufficient data)."""
    check = CorrectionIntakeCheck(db_with_atomic_ops)
    results = check.run()

    assert len(results) == 1
    assert results[0].severity == Severity.HEALTHY
    assert "0 operations" in results[0].title
    assert "Not enough data yet" in results[0].title
    assert results[0].finding_key == "correction_intake:insufficient_data"


def test_insufficient_operations_returns_healthy(db_with_atomic_ops):
    """With <10 operations, check should return healthy with insufficient data message."""
    conn = db_with_atomic_ops.connect()

    # Create 5 operations (below threshold)
    for i in range(5):
        conn.execute(
            """
            INSERT INTO atomic_operations (
                id, user_request, user_id, status, created_at
            ) VALUES (?, ?, 'local', 'complete', datetime('now'))
            """,
            (f"op-{i}", f"request {i}"),
        )
    conn.commit()
    conn.close()

    check = CorrectionIntakeCheck(db_with_atomic_ops)
    results = check.run()

    assert len(results) == 1
    assert results[0].severity == Severity.HEALTHY
    assert "5 operations" in results[0].title
    assert "Not enough data yet" in results[0].title
    assert "Need at least 10" in results[0].details
    assert results[0].finding_key == "correction_intake:insufficient_data"


def test_low_correction_rate_returns_healthy(db_with_atomic_ops):
    """Correction rate <15% should return healthy."""
    conn = db_with_atomic_ops.connect()

    # Create 20 operations with 2 corrections (10% correction rate)
    for i in range(20):
        op_id = f"op-{i}"
        conn.execute(
            """
            INSERT INTO atomic_operations (
                id, user_request, user_id, status, created_at
            ) VALUES (?, ?, 'local', 'complete', datetime('now'))
            """,
            (op_id, f"request {i}"),
        )

        # Add approval feedback for all
        if i < 2:
            # First 2 are corrections
            conn.execute(
                """
                INSERT INTO user_feedback (
                    id, operation_id, user_id, feedback_type,
                    system_classification, user_corrected_destination,
                    created_at
                ) VALUES (?, ?, 'local', 'correction', '{}', 'file', datetime('now'))
                """,
                (f"fb-{i}", op_id),
            )
        else:
            # Rest are approvals
            conn.execute(
                """
                INSERT INTO user_feedback (
                    id, operation_id, user_id, feedback_type,
                    approved, created_at
                ) VALUES (?, ?, 'local', 'approval', 1, datetime('now'))
                """,
                (f"fb-{i}", op_id),
            )

    conn.commit()
    conn.close()

    check = CorrectionIntakeCheck(db_with_atomic_ops)
    results = check.run()

    assert len(results) == 1
    assert results[0].severity == Severity.HEALTHY
    assert "90%" in results[0].title  # 90% accuracy
    assert results[0].finding_key == "correction_intake:ok"


def test_moderate_correction_rate_returns_warning(db_with_atomic_ops):
    """Correction rate 15-30% should return warning."""
    conn = db_with_atomic_ops.connect()

    # Create 20 operations with 4 corrections (20% correction rate)
    for i in range(20):
        op_id = f"op-{i}"
        conn.execute(
            """
            INSERT INTO atomic_operations (
                id, user_request, user_id, status, created_at
            ) VALUES (?, ?, 'local', 'complete', datetime('now'))
            """,
            (op_id, f"request {i}"),
        )

        if i < 4:
            # First 4 are corrections
            conn.execute(
                """
                INSERT INTO user_feedback (
                    id, operation_id, user_id, feedback_type,
                    system_classification, user_corrected_destination,
                    created_at
                ) VALUES (?, ?, 'local', 'correction', '{}', 'file', datetime('now'))
                """,
                (f"fb-{i}", op_id),
            )
        else:
            # Rest are approvals
            conn.execute(
                """
                INSERT INTO user_feedback (
                    id, operation_id, user_id, feedback_type,
                    approved, created_at
                ) VALUES (?, ?, 'local', 'approval', 1, datetime('now'))
                """,
                (f"fb-{i}", op_id),
            )

    conn.commit()
    conn.close()

    check = CorrectionIntakeCheck(db_with_atomic_ops)
    results = check.run()

    assert len(results) == 1
    assert results[0].severity == Severity.WARNING
    assert "Moderate correction rate: 20%" in results[0].title
    assert "20 feedback entries" in results[0].details
    assert "Worth monitoring" in results[0].details
    assert "correction_intake:moderate:0.20" == results[0].finding_key


def test_high_correction_rate_returns_critical(db_with_atomic_ops):
    """Correction rate >30% should return critical."""
    conn = db_with_atomic_ops.connect()

    # Create 20 operations with 8 corrections (40% correction rate)
    for i in range(20):
        op_id = f"op-{i}"
        conn.execute(
            """
            INSERT INTO atomic_operations (
                id, user_request, user_id, status, created_at
            ) VALUES (?, ?, 'local', 'complete', datetime('now'))
            """,
            (op_id, f"request {i}"),
        )

        if i < 8:
            # First 8 are corrections
            conn.execute(
                """
                INSERT INTO user_feedback (
                    id, operation_id, user_id, feedback_type,
                    system_classification, user_corrected_destination,
                    created_at
                ) VALUES (?, ?, 'local', 'correction', '{}', 'file', datetime('now'))
                """,
                (f"fb-{i}", op_id),
            )
        else:
            # Rest are approvals
            conn.execute(
                """
                INSERT INTO user_feedback (
                    id, operation_id, user_id, feedback_type,
                    approved, created_at
                ) VALUES (?, ?, 'local', 'approval', 1, datetime('now'))
                """,
                (f"fb-{i}", op_id),
            )

    conn.commit()
    conn.close()

    check = CorrectionIntakeCheck(db_with_atomic_ops)
    results = check.run()

    assert len(results) == 1
    assert results[0].severity == Severity.CRITICAL
    assert "High correction rate: 40%" in results[0].title
    assert "20 feedback entries" in results[0].details
    assert "may need retuning" in results[0].details
    assert "correction_intake:high:0.40" == results[0].finding_key


def test_exactly_at_warning_threshold(db_with_atomic_ops):
    """Correction rate exactly at 15% should trigger warning."""
    conn = db_with_atomic_ops.connect()

    # Create 20 operations with 3 corrections (15% correction rate)
    for i in range(20):
        op_id = f"op-{i}"
        conn.execute(
            """
            INSERT INTO atomic_operations (
                id, user_request, user_id, status, created_at
            ) VALUES (?, ?, 'local', 'complete', datetime('now'))
            """,
            (op_id, f"request {i}"),
        )

        if i < 3:
            # First 3 are corrections
            conn.execute(
                """
                INSERT INTO user_feedback (
                    id, operation_id, user_id, feedback_type,
                    system_classification, user_corrected_destination,
                    created_at
                ) VALUES (?, ?, 'local', 'correction', '{}', 'file', datetime('now'))
                """,
                (f"fb-{i}", op_id),
            )
        else:
            # Rest are approvals
            conn.execute(
                """
                INSERT INTO user_feedback (
                    id, operation_id, user_id, feedback_type,
                    approved, created_at
                ) VALUES (?, ?, 'local', 'approval', 1, datetime('now'))
                """,
                (f"fb-{i}", op_id),
            )

    conn.commit()
    conn.close()

    check = CorrectionIntakeCheck(db_with_atomic_ops)
    results = check.run()

    assert len(results) == 1
    assert results[0].severity == Severity.WARNING
    assert "15%" in results[0].title


def test_exactly_at_critical_threshold(db_with_atomic_ops):
    """Correction rate exactly at 30% should trigger critical."""
    conn = db_with_atomic_ops.connect()

    # Create 20 operations with 6 corrections (30% correction rate)
    for i in range(20):
        op_id = f"op-{i}"
        conn.execute(
            """
            INSERT INTO atomic_operations (
                id, user_request, user_id, status, created_at
            ) VALUES (?, ?, 'local', 'complete', datetime('now'))
            """,
            (op_id, f"request {i}"),
        )

        if i < 6:
            # First 6 are corrections
            conn.execute(
                """
                INSERT INTO user_feedback (
                    id, operation_id, user_id, feedback_type,
                    system_classification, user_corrected_destination,
                    created_at
                ) VALUES (?, ?, 'local', 'correction', '{}', 'file', datetime('now'))
                """,
                (f"fb-{i}", op_id),
            )
        else:
            # Rest are approvals
            conn.execute(
                """
                INSERT INTO user_feedback (
                    id, operation_id, user_id, feedback_type,
                    approved, created_at
                ) VALUES (?, ?, 'local', 'approval', 1, datetime('now'))
                """,
                (f"fb-{i}", op_id),
            )

    conn.commit()
    conn.close()

    check = CorrectionIntakeCheck(db_with_atomic_ops)
    results = check.run()

    assert len(results) == 1
    assert results[0].severity == Severity.CRITICAL
    assert "30%" in results[0].title
