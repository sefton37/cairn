"""Tests for RIVA execution metrics collection.

These tests verify that metrics are properly collected during RIVA execution.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

import pytest

from reos.code_mode.optimization.metrics import (
    ExecutionMetrics,
    MetricsStore,
    create_metrics,
)


class TestExecutionMetrics:
    """Test ExecutionMetrics dataclass."""

    def test_create_metrics(self) -> None:
        """Test basic metrics creation."""
        metrics = create_metrics("test-session-123")

        assert metrics.session_id == "test-session-123"
        assert metrics.llm_calls_total == 0
        assert metrics.decomposition_count == 0
        assert metrics.success is False
        assert metrics.started_at is not None

    def test_record_llm_call(self) -> None:
        """Test recording LLM calls."""
        metrics = create_metrics("test")

        metrics.record_llm_call("action", 1500)
        metrics.record_llm_call("action", 2000)
        metrics.record_llm_call("decomposition", 1000)

        assert metrics.llm_calls_total == 3
        assert metrics.llm_calls_action == 2
        assert metrics.llm_calls_decomposition == 1
        assert metrics.llm_time_ms == 4500

    def test_record_decomposition(self) -> None:
        """Test recording decompositions."""
        metrics = create_metrics("test")

        metrics.record_decomposition(depth=1)
        metrics.record_decomposition(depth=2)
        metrics.record_decomposition(depth=3)

        assert metrics.decomposition_count == 3
        assert metrics.max_depth_reached == 3

    def test_record_verification(self) -> None:
        """Test recording verifications by risk level."""
        metrics = create_metrics("test")

        metrics.record_verification("high")
        metrics.record_verification("high")
        metrics.record_verification("medium")
        metrics.record_verification("low")

        assert metrics.verifications_total == 4
        assert metrics.verifications_high_risk == 2
        assert metrics.verifications_medium_risk == 1
        assert metrics.verifications_low_risk == 1

    def test_record_retry_and_failure(self) -> None:
        """Test recording retries and failures."""
        metrics = create_metrics("test")

        metrics.record_retry()
        metrics.record_retry()
        metrics.record_failure()

        assert metrics.retry_count == 2
        assert metrics.failure_count == 1

    def test_complete_success(self) -> None:
        """Test completing metrics with success."""
        metrics = create_metrics("test")

        # Simulate some work
        time.sleep(0.01)  # 10ms

        metrics.complete(success=True)

        assert metrics.success is True
        assert metrics.first_try_success is True  # No retries
        assert metrics.completed_at is not None
        assert metrics.total_duration_ms >= 10

    def test_complete_failure_with_retries(self) -> None:
        """Test completing metrics with failure after retries."""
        metrics = create_metrics("test")

        metrics.record_retry()
        metrics.record_retry()
        metrics.complete(success=False)

        assert metrics.success is False
        assert metrics.first_try_success is False
        assert metrics.retry_count == 2

    def test_complete_success_with_retries(self) -> None:
        """Test that success with retries is not first-try success."""
        metrics = create_metrics("test")

        metrics.record_retry()
        metrics.complete(success=True)

        assert metrics.success is True
        assert metrics.first_try_success is False  # Had retries

    def test_to_dict(self) -> None:
        """Test serialization to dictionary."""
        metrics = create_metrics("test-123")
        metrics.record_llm_call("action", 1000)
        metrics.record_decomposition(depth=1)
        metrics.complete(success=True)

        data = metrics.to_dict()

        assert data["session_id"] == "test-123"
        assert data["llm_calls"]["total"] == 1
        assert data["decomposition"]["count"] == 1
        assert data["outcome"]["success"] is True

    def test_summary(self) -> None:
        """Test human-readable summary."""
        metrics = create_metrics("test-abc")
        metrics.record_llm_call("action", 1000)
        metrics.record_llm_call("action", 1000)
        metrics.record_decomposition(depth=1)
        metrics.record_verification("medium")
        metrics.complete(success=True)

        summary = metrics.summary()

        assert "test-abc" in summary
        assert "SUCCESS" in summary
        assert "2 LLM calls" in summary
        assert "1 decompositions" in summary
        assert "1 verifications" in summary


class TestMetricsStore:
    """Test MetricsStore database persistence."""

    @pytest.fixture
    def mock_db(self) -> "MockDatabase":
        """Create a mock database for testing."""
        return MockDatabase()

    def test_ensure_table(self, mock_db: "MockDatabase") -> None:
        """Test that table and index are created on init."""
        store = MetricsStore(mock_db)

        # Now creates table + index
        assert len(mock_db.executed) == 2
        assert "CREATE TABLE" in mock_db.executed[0]
        assert "riva_metrics" in mock_db.executed[0]
        assert "CREATE INDEX" in mock_db.executed[1]

    def test_save_metrics(self, mock_db: "MockDatabase") -> None:
        """Test saving metrics to database."""
        store = MetricsStore(mock_db)

        metrics = create_metrics("test-save")
        metrics.record_llm_call("action", 1500)
        metrics.complete(success=True)

        store.save(metrics)

        # Should have table creation + index + insert
        assert len(mock_db.executed) == 3
        assert "INSERT OR REPLACE" in mock_db.executed[2]

    def test_get_baseline_stats_empty(self, mock_db: "MockDatabase") -> None:
        """Test getting baseline stats with no data."""
        mock_db.fetchall_result = [[None] * 9]

        store = MetricsStore(mock_db)
        stats = store.get_baseline_stats()

        # Should handle empty gracefully
        assert "sample_size" in stats or "error" in stats

    def test_get_baseline_stats_with_data(self, mock_db: "MockDatabase") -> None:
        """Test getting baseline stats with data."""
        mock_db.fetchall_result = [[
            10,     # total_sessions
            5000.0, # avg_duration_ms
            3000.0, # avg_llm_time_ms
            3.5,    # avg_llm_calls
            1.2,    # avg_decompositions
            4.0,    # avg_verifications
            8,      # success_count
            6,      # first_try_count
            1.5,    # avg_depth
        ]]

        store = MetricsStore(mock_db)
        stats = store.get_baseline_stats()

        assert stats["sample_size"] == 10
        assert stats["avg_duration_ms"] == 5000.0
        assert stats["success_rate"] == 80.0  # 8/10
        assert stats["first_try_rate"] == 60.0  # 6/10

    def test_get_recent(self, mock_db: "MockDatabase") -> None:
        """Test getting recent metrics."""
        mock_db.fetchall_result = [
            ("session-1", "2025-01-01T10:00:00", 5000, 3, 1, 1),
            ("session-2", "2025-01-01T09:00:00", 6000, 4, 2, 0),
        ]

        store = MetricsStore(mock_db)
        recent = store.get_recent(limit=10)

        assert len(recent) == 2
        assert recent[0]["session_id"] == "session-1"
        assert recent[0]["success"] is True
        assert recent[1]["success"] is False


class MockDatabase:
    """Mock database for testing."""

    def __init__(self) -> None:
        self.executed: list[str] = []
        self.fetchall_result: list = []

    def execute(self, sql: str, params: tuple = ()) -> None:
        self.executed.append(sql)

    def fetchall(self, sql: str, params: tuple = ()) -> list:
        self.executed.append(sql)
        return self.fetchall_result

    def fetchone(self, sql: str, params: tuple = ()) -> tuple | None:
        self.executed.append(sql)
        return self.fetchall_result[0] if self.fetchall_result else None
