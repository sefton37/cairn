"""Optimization status reporting.

This module provides a unified view of all RIVA optimization
components for debugging and observability.

Usage:
    from reos.code_mode.optimization.status import OptimizationStatus

    status = OptimizationStatus(ctx)
    print(status.summary())
    data = status.to_dict()
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from reos.code_mode.intention import WorkContext
    from reos.code_mode.optimization.metrics import ExecutionMetrics
    from reos.code_mode.optimization.trust import TrustBudget
    from reos.code_mode.optimization.verification import VerificationBatcher


@dataclass
class OptimizationStatus:
    """Aggregated status of all optimization components.

    Provides a single view into:
    - Metrics collection (LLM calls, timing, success rates)
    - Trust budget (current level, verifications skipped)
    - Verification batcher (pending verifications)

    Attributes:
        metrics: ExecutionMetrics instance (or None)
        trust_budget: TrustBudget instance (or None)
        verification_batcher: VerificationBatcher instance (or None)
    """

    metrics: "ExecutionMetrics | None"
    trust_budget: "TrustBudget | None"
    verification_batcher: "VerificationBatcher | None"

    @classmethod
    def from_context(cls, ctx: "WorkContext") -> "OptimizationStatus":
        """Create status from WorkContext.

        Args:
            ctx: WorkContext with optimization components

        Returns:
            OptimizationStatus instance
        """
        return cls(
            metrics=ctx.metrics,
            trust_budget=ctx.trust_budget,
            verification_batcher=ctx.verification_batcher,
        )

    @property
    def is_active(self) -> bool:
        """Are any optimization components active?"""
        return any([
            self.metrics is not None,
            self.trust_budget is not None,
            self.verification_batcher is not None,
        ])

    @property
    def components_enabled(self) -> list[str]:
        """List of enabled optimization components."""
        components = []
        if self.metrics:
            components.append("metrics")
        if self.trust_budget:
            components.append("trust_budget")
        if self.verification_batcher:
            components.append("verification_batcher")
        return components

    def summary(self) -> str:
        """Generate human-readable summary.

        Returns:
            Multi-line summary string
        """
        lines = ["=== RIVA Optimization Status ==="]

        if not self.is_active:
            lines.append("No optimization components enabled")
            return "\n".join(lines)

        lines.append(f"Components: {', '.join(self.components_enabled)}")
        lines.append("")

        # Metrics summary
        if self.metrics:
            lines.append("--- Metrics ---")
            lines.append(f"  Session: {self.metrics.session_id}")
            lines.append(f"  LLM Calls: {self.metrics.llm_calls_total}")
            lines.append(f"    Action: {self.metrics.llm_calls_action}")
            lines.append(f"    Decomposition: {self.metrics.llm_calls_decomposition}")
            lines.append(f"  LLM Time: {self.metrics.llm_time_ms:.0f}ms")
            lines.append(f"  Decompositions: {self.metrics.decomposition_count}")
            lines.append(f"  Max Depth: {self.metrics.max_depth_reached}")
            lines.append(f"  Verifications: {self.metrics.verifications_total}")
            lines.append(f"    High Risk: {self.metrics.verifications_high_risk}")
            lines.append(f"    Medium Risk: {self.metrics.verifications_medium_risk}")
            lines.append(f"    Low Risk: {self.metrics.verifications_low_risk}")
            lines.append(f"  Retries: {self.metrics.retry_count}")
            lines.append(f"  Failures: {self.metrics.failure_count}")
            if self.metrics.completed_at:
                lines.append(f"  Total Duration: {self.metrics.total_duration_ms:.0f}ms")
                lines.append(f"  Success: {self.metrics.success}")
            lines.append("")

        # Trust budget summary
        if self.trust_budget:
            lines.append("--- Trust Budget ---")
            lines.append(f"  Level: {self.trust_budget.remaining}/{self.trust_budget.initial} ({self.trust_budget.trust_level:.0%})")
            lines.append(f"  Mode: {'HIGH' if self.trust_budget.is_high_trust else 'LOW' if self.trust_budget.is_low_trust else 'NORMAL'}")
            lines.append(f"  Verifications Performed: {self.trust_budget.verifications_performed}")
            lines.append(f"  Verifications Skipped: {self.trust_budget.verifications_skipped}")
            lines.append(f"  Failures Caught: {self.trust_budget.failures_caught}")
            lines.append(f"  Failures Missed: {self.trust_budget.failures_missed}")
            lines.append("")

        # Verification batcher summary
        if self.verification_batcher:
            lines.append("--- Verification Batcher ---")
            lines.append(f"  Pending: {self.verification_batcher.pending_count}")
            if self.verification_batcher.has_pending():
                lines.append("  Status: DEFERRED (will flush at boundary)")
            else:
                lines.append("  Status: EMPTY")
            lines.append("")

        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """Serialize status to dictionary.

        Returns:
            Dictionary with all status data
        """
        data: dict[str, Any] = {
            "is_active": self.is_active,
            "components_enabled": self.components_enabled,
        }

        if self.metrics:
            data["metrics"] = self.metrics.to_dict()

        if self.trust_budget:
            data["trust_budget"] = self.trust_budget.to_dict()

        if self.verification_batcher:
            data["verification_batcher"] = {
                "pending_count": self.verification_batcher.pending_count,
                "has_pending": self.verification_batcher.has_pending(),
            }

        return data

    def get_efficiency_metrics(self) -> dict[str, float]:
        """Calculate efficiency metrics.

        Returns:
            Dictionary with efficiency percentages
        """
        metrics: dict[str, float] = {}

        if self.trust_budget:
            total_checks = (
                self.trust_budget.verifications_performed +
                self.trust_budget.verifications_skipped
            )
            if total_checks > 0:
                metrics["verification_skip_rate"] = (
                    self.trust_budget.verifications_skipped / total_checks * 100
                )
            else:
                metrics["verification_skip_rate"] = 0.0

            if self.trust_budget.failures_caught + self.trust_budget.failures_missed > 0:
                metrics["failure_catch_rate"] = (
                    self.trust_budget.failures_caught /
                    (self.trust_budget.failures_caught + self.trust_budget.failures_missed) * 100
                )
            else:
                metrics["failure_catch_rate"] = 100.0  # No failures = perfect

        if self.metrics:
            if self.metrics.verifications_total > 0:
                metrics["high_risk_rate"] = (
                    self.metrics.verifications_high_risk /
                    self.metrics.verifications_total * 100
                )
            else:
                metrics["high_risk_rate"] = 0.0

            if self.metrics.llm_calls_total > 0 and self.metrics.total_duration_ms > 0:
                metrics["llm_time_percentage"] = (
                    self.metrics.llm_time_ms / self.metrics.total_duration_ms * 100
                )
            else:
                metrics["llm_time_percentage"] = 0.0

        return metrics


def create_status(ctx: "WorkContext") -> OptimizationStatus:
    """Create optimization status from context.

    Convenience function for creating status.

    Args:
        ctx: WorkContext with optimization components

    Returns:
        OptimizationStatus instance
    """
    return OptimizationStatus.from_context(ctx)
