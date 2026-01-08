"""Quality Tier Tracking - Transparency over hidden failures.

This module implements the Local-First Reliability Philosophy:
- Build for unreliable LLM responses as the norm
- Every fallback layer produces useful output
- Execution is ground truth ("verified" = executed, not just created)
- When quality degrades, the user knows

QUALITY TIERS:
- TIER 1 (LLM_SUCCESS): Full LLM-driven generation
- TIER 2 (HEURISTIC_FALLBACK): LLM failed, smart heuristics used
- TIER 3 (PATTERN_FALLBACK): Pattern-based generation, needs review

Usage:
    tracker = QualityTracker()

    with tracker.track_operation("decomposition") as op:
        try:
            result = llm.chat_json(...)
            op.mark_llm_success()
        except Exception as e:
            op.mark_fallback("JSON parse failed", e)
            result = heuristic_fallback()

    # Later: check overall quality
    if tracker.current_tier == QualityTier.PATTERN_FALLBACK:
        notify_user("[QUALITY: TIER 3] Some operations used pattern-based fallbacks")
"""

from __future__ import annotations

import logging
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from reos.code_mode.session_logger import SessionLogger

logger = logging.getLogger(__name__)


# =============================================================================
# Quality Tiers
# =============================================================================


class QualityTier(IntEnum):
    """Quality tiers ordered from best to worst.

    Using IntEnum allows comparison: TIER_1 > TIER_2 > TIER_3
    """

    LLM_SUCCESS = 1         # Full LLM-driven, verified
    HEURISTIC_FALLBACK = 2  # LLM failed, smart heuristics used
    PATTERN_FALLBACK = 3    # Pattern-based, needs manual review
    UNKNOWN = 4             # Not yet determined


TIER_DISPLAY = {
    QualityTier.LLM_SUCCESS: ("TIER 1", "LLM generated verified code", "success"),
    QualityTier.HEURISTIC_FALLBACK: ("TIER 2", "Heuristic fallback (LLM failed)", "warning"),
    QualityTier.PATTERN_FALLBACK: ("TIER 3", "Pattern-based generation (needs review)", "warning"),
    QualityTier.UNKNOWN: ("UNKNOWN", "Quality not yet determined", "info"),
}


# =============================================================================
# Quality Events
# =============================================================================


@dataclass
class QualityEvent:
    """A single quality-affecting event during execution."""

    timestamp: datetime
    operation: str  # e.g., "decomposition", "action_determination", "test_generation"
    tier: QualityTier
    reason: str  # Why this tier? e.g., "LLM returned valid JSON"
    exception: str | None = None  # If failed, what exception?
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for logging/UI."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "operation": self.operation,
            "tier": self.tier.name,
            "tier_value": self.tier.value,
            "reason": self.reason,
            "exception": self.exception,
            "context": self.context,
        }


# =============================================================================
# Operation Tracker (Context Manager)
# =============================================================================


@dataclass
class OperationTracker:
    """Tracks quality for a single operation. Use as context manager."""

    quality_tracker: QualityTracker
    operation: str
    start_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    tier: QualityTier = QualityTier.UNKNOWN
    reason: str = ""
    exception: str | None = None
    context: dict[str, Any] = field(default_factory=dict)
    _finalized: bool = False

    def mark_llm_success(self, reason: str = "LLM returned valid response") -> None:
        """Mark this operation as successful LLM-driven."""
        self.tier = QualityTier.LLM_SUCCESS
        self.reason = reason

    def mark_fallback(
        self,
        reason: str,
        exception: Exception | None = None,
        tier: QualityTier = QualityTier.HEURISTIC_FALLBACK,
    ) -> None:
        """Mark this operation as using fallback."""
        self.tier = tier
        self.reason = reason
        if exception:
            self.exception = f"{type(exception).__name__}: {exception}"

    def mark_pattern_fallback(self, reason: str = "Using pattern-based generation") -> None:
        """Mark this operation as using pattern-based fallback (lowest tier)."""
        self.tier = QualityTier.PATTERN_FALLBACK
        self.reason = reason

    def add_context(self, **kwargs: Any) -> None:
        """Add context information for debugging."""
        self.context.update(kwargs)

    def finalize(self) -> QualityEvent:
        """Create the final quality event."""
        if self._finalized:
            raise RuntimeError("Operation already finalized")
        self._finalized = True

        # If nothing was marked, assume unknown/failure
        if self.tier == QualityTier.UNKNOWN and not self.reason:
            self.reason = "Operation completed without quality marking"

        event = QualityEvent(
            timestamp=self.start_time,
            operation=self.operation,
            tier=self.tier,
            reason=self.reason,
            exception=self.exception,
            context=self.context,
        )
        return event


# =============================================================================
# Quality Tracker
# =============================================================================


class QualityTracker:
    """Tracks quality across an entire execution session.

    Thread-safe. Integrates with SessionLogger for persistence.

    The current_tier is the WORST tier seen across all operations.
    This ensures transparency: if any operation degraded, the user knows.
    """

    def __init__(self, session_logger: SessionLogger | None = None) -> None:
        self._lock = threading.Lock()
        self._events: list[QualityEvent] = []
        self._current_tier = QualityTier.UNKNOWN
        self._session_logger = session_logger
        self._observers: list[Callable[[QualityEvent], None]] = []

    @property
    def current_tier(self) -> QualityTier:
        """Get the worst quality tier seen so far."""
        with self._lock:
            return self._current_tier

    @property
    def events(self) -> list[QualityEvent]:
        """Get all quality events (copy for thread safety)."""
        with self._lock:
            return list(self._events)

    def add_observer(self, callback: Callable[[QualityEvent], None]) -> None:
        """Add observer to be notified of quality events."""
        with self._lock:
            self._observers.append(callback)

    def remove_observer(self, callback: Callable[[QualityEvent], None]) -> None:
        """Remove an observer."""
        with self._lock:
            self._observers.remove(callback)

    @contextmanager
    def track_operation(self, operation: str):
        """Context manager for tracking a single operation's quality.

        Usage:
            with tracker.track_operation("decomposition") as op:
                try:
                    result = llm.chat_json(...)
                    op.mark_llm_success()
                except JSONDecodeError as e:
                    op.mark_fallback("JSON parse failed", e)
                    result = heuristic_fallback()
        """
        op = OperationTracker(quality_tracker=self, operation=operation)
        try:
            yield op
        finally:
            event = op.finalize()
            self._record_event(event)

    def record_event(
        self,
        operation: str,
        tier: QualityTier,
        reason: str,
        exception: Exception | None = None,
        context: dict[str, Any] | None = None,
    ) -> QualityEvent:
        """Directly record a quality event without context manager."""
        event = QualityEvent(
            timestamp=datetime.now(timezone.utc),
            operation=operation,
            tier=tier,
            reason=reason,
            exception=f"{type(exception).__name__}: {exception}" if exception else None,
            context=context or {},
        )
        self._record_event(event)
        return event

    def _record_event(self, event: QualityEvent) -> None:
        """Internal: record event and update current tier."""
        with self._lock:
            self._events.append(event)

            # Update current tier to worst seen
            # Higher tier value = worse quality
            if event.tier > self._current_tier or self._current_tier == QualityTier.UNKNOWN:
                if event.tier != QualityTier.UNKNOWN:
                    self._current_tier = event.tier

            # Log to session logger if available
            if self._session_logger:
                level = "INFO" if event.tier == QualityTier.LLM_SUCCESS else "WARN"
                self._session_logger.log(
                    module="quality",
                    action=f"quality_{event.operation}",
                    details=event.to_dict(),
                    level=level,
                )

            # Notify observers
            observers = list(self._observers)

        # Notify outside lock to prevent deadlock
        for observer in observers:
            try:
                observer(event)
            except Exception as e:
                logger.warning("Quality observer failed: %s", e)

    def get_summary(self) -> dict[str, Any]:
        """Get quality summary for UI display."""
        with self._lock:
            tier_counts = {t.name: 0 for t in QualityTier}
            for event in self._events:
                tier_counts[event.tier.name] += 1

            tier_label, tier_desc, tier_severity = TIER_DISPLAY[self._current_tier]

            return {
                "overall_tier": self._current_tier.name,
                "overall_tier_value": self._current_tier.value,
                "tier_label": tier_label,
                "tier_description": tier_desc,
                "tier_severity": tier_severity,
                "total_operations": len(self._events),
                "tier_counts": tier_counts,
                "llm_success_rate": (
                    tier_counts["LLM_SUCCESS"] / len(self._events) * 100
                    if self._events else 0.0
                ),
                "fallback_operations": [
                    e.to_dict() for e in self._events
                    if e.tier >= QualityTier.HEURISTIC_FALLBACK
                ],
            }

    def get_user_message(self) -> str | None:
        """Get user-facing quality message, or None if all good."""
        summary = self.get_summary()
        tier = self._current_tier

        if tier == QualityTier.LLM_SUCCESS:
            return None  # No message needed for perfect execution

        label, desc, _ = TIER_DISPLAY[tier]
        fallback_count = len(summary["fallback_operations"])

        return f"[QUALITY: {label}] {desc} ({fallback_count} operations used fallbacks)"

    def reset(self) -> None:
        """Reset tracker for new execution."""
        with self._lock:
            self._events.clear()
            self._current_tier = QualityTier.UNKNOWN


# =============================================================================
# Global Quality Context (for thread-local tracking)
# =============================================================================


_quality_context = threading.local()


def get_current_tracker() -> QualityTracker | None:
    """Get the current thread's quality tracker."""
    return getattr(_quality_context, "tracker", None)


def set_current_tracker(tracker: QualityTracker | None) -> None:
    """Set the current thread's quality tracker."""
    _quality_context.tracker = tracker


@contextmanager
def quality_context(tracker: QualityTracker):
    """Context manager to set thread-local quality tracker."""
    old = get_current_tracker()
    set_current_tracker(tracker)
    try:
        yield tracker
    finally:
        set_current_tracker(old)


def track_quality(operation: str):
    """Decorator/context manager for quality tracking with global tracker.

    Usage as context manager:
        with track_quality("decomposition") as op:
            ...
            op.mark_llm_success()

    If no tracker is set in current context, creates a no-op tracker.
    """
    tracker = get_current_tracker()
    if tracker is None:
        # No-op tracker for when quality tracking isn't enabled
        return _NoopOperationContext()
    return tracker.track_operation(operation)


class _NoopOperationContext:
    """No-op context for when quality tracking is disabled."""

    def __enter__(self):
        return _NoopOperationTracker()

    def __exit__(self, *args):
        pass


class _NoopOperationTracker:
    """No-op operation tracker."""

    def mark_llm_success(self, reason: str = "") -> None:
        pass

    def mark_fallback(self, reason: str, exception: Exception | None = None, tier: QualityTier = QualityTier.HEURISTIC_FALLBACK) -> None:
        pass

    def mark_pattern_fallback(self, reason: str = "") -> None:
        pass

    def add_context(self, **kwargs: Any) -> None:
        pass


# =============================================================================
# Convenience Functions
# =============================================================================


def format_quality_for_log(tier: QualityTier) -> str:
    """Format quality tier for log output."""
    label, desc, severity = TIER_DISPLAY[tier]
    icons = {"success": "\u2713", "warning": "\u26a0", "info": "\u2139"}
    icon = icons.get(severity, "")
    return f"[QUALITY: {label}] {icon} {desc}"
