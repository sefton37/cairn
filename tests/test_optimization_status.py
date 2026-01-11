"""Tests for optimization status reporting.

Tests that the status module correctly aggregates and reports
optimization component state.
"""

from __future__ import annotations

import pytest

from reos.code_mode.optimization.status import (
    OptimizationStatus,
    create_status,
)
from reos.code_mode.optimization.metrics import create_metrics
from reos.code_mode.optimization.trust import create_trust_budget
from reos.code_mode.optimization.verification import VerificationBatcher


class MockWorkContext:
    """Mock WorkContext for testing."""

    def __init__(
        self,
        metrics=None,
        trust_budget=None,
        verification_batcher=None,
    ):
        self.metrics = metrics
        self.trust_budget = trust_budget
        self.verification_batcher = verification_batcher


class TestOptimizationStatusCreation:
    """Test OptimizationStatus creation."""

    def test_create_empty_status(self) -> None:
        """Create status with no components."""
        status = OptimizationStatus(
            metrics=None,
            trust_budget=None,
            verification_batcher=None,
        )

        assert status.is_active is False
        assert status.components_enabled == []

    def test_create_from_context(self) -> None:
        """Create status from WorkContext."""
        metrics = create_metrics("test-session")
        trust = create_trust_budget()
        batcher = VerificationBatcher()

        ctx = MockWorkContext(
            metrics=metrics,
            trust_budget=trust,
            verification_batcher=batcher,
        )

        status = OptimizationStatus.from_context(ctx)

        assert status.is_active is True
        assert "metrics" in status.components_enabled
        assert "trust_budget" in status.components_enabled
        assert "verification_batcher" in status.components_enabled

    def test_create_with_convenience_function(self) -> None:
        """Test create_status convenience function."""
        metrics = create_metrics("test")
        ctx = MockWorkContext(metrics=metrics)

        status = create_status(ctx)

        assert status.metrics is metrics


class TestComponentsEnabled:
    """Test components_enabled property."""

    def test_only_metrics(self) -> None:
        """Only metrics enabled."""
        status = OptimizationStatus(
            metrics=create_metrics("test"),
            trust_budget=None,
            verification_batcher=None,
        )

        assert status.components_enabled == ["metrics"]

    def test_only_trust_budget(self) -> None:
        """Only trust budget enabled."""
        status = OptimizationStatus(
            metrics=None,
            trust_budget=create_trust_budget(),
            verification_batcher=None,
        )

        assert status.components_enabled == ["trust_budget"]

    def test_only_batcher(self) -> None:
        """Only verification batcher enabled."""
        status = OptimizationStatus(
            metrics=None,
            trust_budget=None,
            verification_batcher=VerificationBatcher(),
        )

        assert status.components_enabled == ["verification_batcher"]

    def test_all_components(self) -> None:
        """All components enabled."""
        status = OptimizationStatus(
            metrics=create_metrics("test"),
            trust_budget=create_trust_budget(),
            verification_batcher=VerificationBatcher(),
        )

        assert len(status.components_enabled) == 3


class TestStatusSummary:
    """Test summary generation."""

    def test_empty_summary(self) -> None:
        """Summary with no components."""
        status = OptimizationStatus(
            metrics=None,
            trust_budget=None,
            verification_batcher=None,
        )

        summary = status.summary()

        assert "RIVA Optimization Status" in summary
        assert "No optimization components enabled" in summary

    def test_summary_with_metrics(self) -> None:
        """Summary includes metrics data."""
        metrics = create_metrics("test-abc")
        metrics.record_llm_call("action", 1000)
        metrics.record_llm_call("action", 2000)
        metrics.record_verification("high")
        metrics.record_decomposition(depth=2)

        status = OptimizationStatus(
            metrics=metrics,
            trust_budget=None,
            verification_batcher=None,
        )

        summary = status.summary()

        assert "test-abc" in summary
        assert "LLM Calls: 2" in summary
        assert "Verifications: 1" in summary
        assert "Decompositions: 1" in summary

    def test_summary_with_trust_budget(self) -> None:
        """Summary includes trust budget data."""
        trust = create_trust_budget(initial=100)
        trust.remaining = 80
        trust.verifications_performed = 5
        trust.verifications_skipped = 3

        status = OptimizationStatus(
            metrics=None,
            trust_budget=trust,
            verification_batcher=None,
        )

        summary = status.summary()

        assert "80/100" in summary
        assert "80%" in summary
        assert "Verifications Performed: 5" in summary
        assert "Verifications Skipped: 3" in summary

    def test_summary_with_batcher(self) -> None:
        """Summary includes batcher data."""
        from reos.code_mode.intention import Action, ActionType

        batcher = VerificationBatcher()
        action = Action(type=ActionType.CREATE, content="test")
        batcher.defer(action, "result", "expected")

        status = OptimizationStatus(
            metrics=None,
            trust_budget=None,
            verification_batcher=batcher,
        )

        summary = status.summary()

        assert "Pending: 1" in summary
        assert "DEFERRED" in summary


class TestStatusSerialization:
    """Test to_dict serialization."""

    def test_empty_to_dict(self) -> None:
        """Serialize empty status."""
        status = OptimizationStatus(
            metrics=None,
            trust_budget=None,
            verification_batcher=None,
        )

        data = status.to_dict()

        assert data["is_active"] is False
        assert data["components_enabled"] == []

    def test_full_to_dict(self) -> None:
        """Serialize status with all components."""
        metrics = create_metrics("test")
        trust = create_trust_budget()
        batcher = VerificationBatcher()

        status = OptimizationStatus(
            metrics=metrics,
            trust_budget=trust,
            verification_batcher=batcher,
        )

        data = status.to_dict()

        assert data["is_active"] is True
        assert "metrics" in data
        assert "trust_budget" in data
        assert "verification_batcher" in data


class TestEfficiencyMetrics:
    """Test efficiency metrics calculation."""

    def test_verification_skip_rate(self) -> None:
        """Calculate verification skip rate."""
        trust = create_trust_budget()
        trust.verifications_performed = 7
        trust.verifications_skipped = 3

        status = OptimizationStatus(
            metrics=None,
            trust_budget=trust,
            verification_batcher=None,
        )

        efficiency = status.get_efficiency_metrics()

        assert efficiency["verification_skip_rate"] == 30.0  # 3/10

    def test_failure_catch_rate(self) -> None:
        """Calculate failure catch rate."""
        trust = create_trust_budget()
        trust.failures_caught = 8
        trust.failures_missed = 2

        status = OptimizationStatus(
            metrics=None,
            trust_budget=trust,
            verification_batcher=None,
        )

        efficiency = status.get_efficiency_metrics()

        assert efficiency["failure_catch_rate"] == 80.0  # 8/10

    def test_perfect_catch_rate_no_failures(self) -> None:
        """No failures means 100% catch rate."""
        trust = create_trust_budget()
        trust.failures_caught = 0
        trust.failures_missed = 0

        status = OptimizationStatus(
            metrics=None,
            trust_budget=trust,
            verification_batcher=None,
        )

        efficiency = status.get_efficiency_metrics()

        assert efficiency["failure_catch_rate"] == 100.0

    def test_high_risk_rate(self) -> None:
        """Calculate high risk verification rate."""
        metrics = create_metrics("test")
        metrics.record_verification("high")
        metrics.record_verification("high")
        metrics.record_verification("medium")
        metrics.record_verification("low")

        status = OptimizationStatus(
            metrics=metrics,
            trust_budget=None,
            verification_batcher=None,
        )

        efficiency = status.get_efficiency_metrics()

        assert efficiency["high_risk_rate"] == 50.0  # 2/4

    def test_empty_efficiency_metrics(self) -> None:
        """Empty status returns empty efficiency."""
        status = OptimizationStatus(
            metrics=None,
            trust_budget=None,
            verification_batcher=None,
        )

        efficiency = status.get_efficiency_metrics()

        assert efficiency == {}


class TestTrustModeDisplay:
    """Test trust mode display in summary."""

    def test_high_trust_mode(self) -> None:
        """High trust mode when >= 80."""
        trust = create_trust_budget(initial=100)
        trust.remaining = 90

        status = OptimizationStatus(
            metrics=None,
            trust_budget=trust,
            verification_batcher=None,
        )

        summary = status.summary()
        assert "Mode: HIGH" in summary

    def test_low_trust_mode(self) -> None:
        """Low trust mode when <= 50."""
        trust = create_trust_budget(initial=100)
        trust.remaining = 40

        status = OptimizationStatus(
            metrics=None,
            trust_budget=trust,
            verification_batcher=None,
        )

        summary = status.summary()
        assert "Mode: LOW" in summary

    def test_normal_trust_mode(self) -> None:
        """Normal trust mode between 50 and 80."""
        trust = create_trust_budget(initial=100)
        trust.remaining = 65

        status = OptimizationStatus(
            metrics=None,
            trust_budget=trust,
            verification_batcher=None,
        )

        summary = status.summary()
        assert "Mode: NORMAL" in summary
