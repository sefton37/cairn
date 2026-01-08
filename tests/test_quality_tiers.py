"""Tests for Quality Tier Tracking module (code_mode.quality).

This tests the Local-First Reliability Philosophy implementation:
- Quality tier tracking (TIER 1/2/3)
- Degradation transparency
- Thread-safe tracking
"""

import pytest
from datetime import datetime, timezone

from reos.code_mode.quality import (
    QualityTier,
    QualityTracker,
    QualityEvent,
    OperationTracker,
    track_quality,
    quality_context,
    get_current_tracker,
    set_current_tracker,
    format_quality_for_log,
    TIER_DISPLAY,
)


class TestQualityTier:
    """Tests for QualityTier enum."""

    def test_tier_ordering(self):
        """Quality tiers should be ordered from best to worst."""
        assert QualityTier.LLM_SUCCESS < QualityTier.HEURISTIC_FALLBACK
        assert QualityTier.HEURISTIC_FALLBACK < QualityTier.PATTERN_FALLBACK
        assert QualityTier.PATTERN_FALLBACK < QualityTier.UNKNOWN

    def test_tier_values(self):
        """Quality tiers should have expected integer values."""
        assert QualityTier.LLM_SUCCESS.value == 1
        assert QualityTier.HEURISTIC_FALLBACK.value == 2
        assert QualityTier.PATTERN_FALLBACK.value == 3
        assert QualityTier.UNKNOWN.value == 4


class TestQualityEvent:
    """Tests for QualityEvent dataclass."""

    def test_event_creation(self):
        """Create a quality event."""
        event = QualityEvent(
            timestamp=datetime.now(timezone.utc),
            operation="test_op",
            tier=QualityTier.LLM_SUCCESS,
            reason="Test reason",
        )
        assert event.operation == "test_op"
        assert event.tier == QualityTier.LLM_SUCCESS
        assert event.reason == "Test reason"
        assert event.exception is None

    def test_event_with_exception(self):
        """Create event with exception info."""
        event = QualityEvent(
            timestamp=datetime.now(timezone.utc),
            operation="failing_op",
            tier=QualityTier.HEURISTIC_FALLBACK,
            reason="JSON parse failed",
            exception="JSONDecodeError: Invalid JSON",
        )
        assert event.exception == "JSONDecodeError: Invalid JSON"

    def test_event_to_dict(self):
        """Event should serialize to dict."""
        event = QualityEvent(
            timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            operation="test_op",
            tier=QualityTier.HEURISTIC_FALLBACK,
            reason="Fallback used",
            context={"key": "value"},
        )
        data = event.to_dict()
        assert data["operation"] == "test_op"
        assert data["tier"] == "HEURISTIC_FALLBACK"
        assert data["tier_value"] == 2
        assert data["reason"] == "Fallback used"
        assert data["context"] == {"key": "value"}


class TestOperationTracker:
    """Tests for OperationTracker context manager."""

    def test_mark_llm_success(self):
        """Mark operation as LLM success."""
        tracker = QualityTracker()
        op = OperationTracker(quality_tracker=tracker, operation="test")
        op.mark_llm_success("Generated valid JSON")
        event = op.finalize()

        assert event.tier == QualityTier.LLM_SUCCESS
        assert event.reason == "Generated valid JSON"

    def test_mark_fallback(self):
        """Mark operation as fallback."""
        tracker = QualityTracker()
        op = OperationTracker(quality_tracker=tracker, operation="test")
        op.mark_fallback("JSON parse failed", ValueError("Invalid"))
        event = op.finalize()

        assert event.tier == QualityTier.HEURISTIC_FALLBACK
        assert "JSON parse failed" in event.reason
        assert "ValueError" in event.exception

    def test_mark_pattern_fallback(self):
        """Mark operation as pattern fallback."""
        tracker = QualityTracker()
        op = OperationTracker(quality_tracker=tracker, operation="test")
        op.mark_pattern_fallback("Using template-based generation")
        event = op.finalize()

        assert event.tier == QualityTier.PATTERN_FALLBACK

    def test_add_context(self):
        """Add context to operation."""
        tracker = QualityTracker()
        op = OperationTracker(quality_tracker=tracker, operation="test")
        op.add_context(model="llama3", tokens=100)
        op.mark_llm_success()
        event = op.finalize()

        assert event.context["model"] == "llama3"
        assert event.context["tokens"] == 100

    def test_double_finalize_raises(self):
        """Finalizing twice should raise."""
        tracker = QualityTracker()
        op = OperationTracker(quality_tracker=tracker, operation="test")
        op.finalize()

        with pytest.raises(RuntimeError):
            op.finalize()


class TestQualityTracker:
    """Tests for QualityTracker."""

    def test_initial_state(self):
        """Tracker starts with unknown tier."""
        tracker = QualityTracker()
        assert tracker.current_tier == QualityTier.UNKNOWN
        assert len(tracker.events) == 0

    def test_track_operation_success(self):
        """Track a successful LLM operation."""
        tracker = QualityTracker()

        with tracker.track_operation("decomposition") as op:
            op.mark_llm_success("Generated 3 sub-tasks")

        assert tracker.current_tier == QualityTier.LLM_SUCCESS
        assert len(tracker.events) == 1
        assert tracker.events[0].operation == "decomposition"

    def test_track_operation_fallback(self):
        """Track operation that falls back."""
        tracker = QualityTracker()

        with tracker.track_operation("decomposition") as op:
            op.mark_fallback("LLM timeout", TimeoutError("Request timed out"))

        assert tracker.current_tier == QualityTier.HEURISTIC_FALLBACK
        assert len(tracker.events) == 1

    def test_worst_tier_tracked(self):
        """Tracker should track the worst tier seen."""
        tracker = QualityTracker()

        # First operation: success
        with tracker.track_operation("op1") as op:
            op.mark_llm_success()

        assert tracker.current_tier == QualityTier.LLM_SUCCESS

        # Second operation: fallback
        with tracker.track_operation("op2") as op:
            op.mark_fallback("Failed")

        # Current tier should now be the worst (fallback)
        assert tracker.current_tier == QualityTier.HEURISTIC_FALLBACK

        # Third operation: success again
        with tracker.track_operation("op3") as op:
            op.mark_llm_success()

        # Still the worst (fallback)
        assert tracker.current_tier == QualityTier.HEURISTIC_FALLBACK

    def test_record_event_directly(self):
        """Record event without context manager."""
        tracker = QualityTracker()
        event = tracker.record_event(
            operation="test_op",
            tier=QualityTier.LLM_SUCCESS,
            reason="Direct recording",
        )

        assert len(tracker.events) == 1
        assert tracker.current_tier == QualityTier.LLM_SUCCESS
        assert event.reason == "Direct recording"

    def test_get_summary(self):
        """Get quality summary."""
        tracker = QualityTracker()

        tracker.record_event("op1", QualityTier.LLM_SUCCESS, "Success 1")
        tracker.record_event("op2", QualityTier.LLM_SUCCESS, "Success 2")
        tracker.record_event("op3", QualityTier.HEURISTIC_FALLBACK, "Fallback")

        summary = tracker.get_summary()

        assert summary["overall_tier"] == "HEURISTIC_FALLBACK"
        assert summary["total_operations"] == 3
        assert summary["tier_counts"]["LLM_SUCCESS"] == 2
        assert summary["tier_counts"]["HEURISTIC_FALLBACK"] == 1
        assert summary["llm_success_rate"] == pytest.approx(66.67, rel=0.1)
        assert len(summary["fallback_operations"]) == 1

    def test_get_user_message_none_for_success(self):
        """No user message for all-success execution."""
        tracker = QualityTracker()
        tracker.record_event("op1", QualityTier.LLM_SUCCESS, "Success")

        assert tracker.get_user_message() is None

    def test_get_user_message_for_fallback(self):
        """User message for fallback execution."""
        tracker = QualityTracker()
        tracker.record_event("op1", QualityTier.HEURISTIC_FALLBACK, "Fallback")

        msg = tracker.get_user_message()
        assert msg is not None
        assert "TIER 2" in msg
        assert "1 operations used fallbacks" in msg

    def test_reset(self):
        """Reset tracker state."""
        tracker = QualityTracker()
        tracker.record_event("op1", QualityTier.HEURISTIC_FALLBACK, "Fallback")

        tracker.reset()

        assert tracker.current_tier == QualityTier.UNKNOWN
        assert len(tracker.events) == 0

    def test_observer_notification(self):
        """Observers are notified of events."""
        tracker = QualityTracker()
        observed_events = []

        def observer(event):
            observed_events.append(event)

        tracker.add_observer(observer)
        tracker.record_event("op1", QualityTier.LLM_SUCCESS, "Success")

        assert len(observed_events) == 1
        assert observed_events[0].operation == "op1"

        tracker.remove_observer(observer)
        tracker.record_event("op2", QualityTier.LLM_SUCCESS, "Success 2")

        assert len(observed_events) == 1  # No new events observed


class TestQualityContext:
    """Tests for thread-local quality context."""

    def test_set_and_get_tracker(self):
        """Set and get thread-local tracker."""
        tracker = QualityTracker()

        assert get_current_tracker() is None
        set_current_tracker(tracker)
        assert get_current_tracker() is tracker
        set_current_tracker(None)
        assert get_current_tracker() is None

    def test_quality_context_manager(self):
        """Quality context manager sets tracker."""
        tracker = QualityTracker()

        assert get_current_tracker() is None

        with quality_context(tracker) as ctx:
            assert ctx is tracker
            assert get_current_tracker() is tracker

        assert get_current_tracker() is None

    def test_track_quality_with_context(self):
        """track_quality uses thread-local tracker."""
        tracker = QualityTracker()

        with quality_context(tracker):
            with track_quality("test_op") as op:
                op.mark_llm_success()

        assert len(tracker.events) == 1
        assert tracker.current_tier == QualityTier.LLM_SUCCESS

    def test_track_quality_without_context(self):
        """track_quality is no-op without tracker."""
        # Should not raise
        with track_quality("test_op") as op:
            op.mark_llm_success()  # No-op


class TestFormatQualityForLog:
    """Tests for format_quality_for_log helper."""

    def test_format_success(self):
        """Format success tier."""
        result = format_quality_for_log(QualityTier.LLM_SUCCESS)
        assert "TIER 1" in result
        assert "LLM generated verified code" in result

    def test_format_fallback(self):
        """Format fallback tier."""
        result = format_quality_for_log(QualityTier.HEURISTIC_FALLBACK)
        assert "TIER 2" in result
        assert "Heuristic fallback" in result


class TestTierDisplay:
    """Tests for TIER_DISPLAY mapping."""

    def test_all_tiers_have_display(self):
        """All quality tiers should have display info."""
        for tier in QualityTier:
            assert tier in TIER_DISPLAY
            label, desc, severity = TIER_DISPLAY[tier]
            assert isinstance(label, str)
            assert isinstance(desc, str)
            assert severity in ("success", "warning", "info")
