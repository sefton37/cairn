"""Integration tests for the full optimization system.

Tests the complete data flow through all optimization components
working together.
"""

from __future__ import annotations

import pytest

from reos.code_mode.intention import Action, ActionType
from reos.code_mode.optimization import (
    # Factory
    create_optimized_context,
    create_minimal_context,
    create_paranoid_context,
    # Status
    create_status,
    OptimizationStatus,
    # Components
    assess_risk,
    analyze_complexity,
    RiskLevel,
)


class MockSandbox:
    """Mock sandbox for integration testing."""
    pass


class MockLLM:
    """Mock LLM for integration testing."""
    pass


class MockCheckpoint:
    """Mock checkpoint for integration testing."""
    pass


class TestFullOptimizationFlow:
    """Test the complete optimization data flow."""

    def test_optimized_context_has_all_components(self) -> None:
        """Verify optimized context has metrics, trust, batcher."""
        ctx = create_optimized_context(
            sandbox=MockSandbox(),
            llm=MockLLM(),
            checkpoint=MockCheckpoint(),
            session_id="integration-test",
        )

        assert ctx.metrics is not None
        assert ctx.trust_budget is not None
        assert ctx.verification_batcher is not None

        # Verify session ID propagated
        assert ctx.metrics.session_id == "integration-test"

    def test_status_reflects_context_state(self) -> None:
        """Status should reflect context optimization state."""
        ctx = create_optimized_context(
            sandbox=MockSandbox(),
            llm=MockLLM(),
            checkpoint=MockCheckpoint(),
        )

        status = create_status(ctx)

        assert status.is_active is True
        assert "metrics" in status.components_enabled
        assert "trust_budget" in status.components_enabled
        assert "verification_batcher" in status.components_enabled

    def test_minimal_context_no_optimizations(self) -> None:
        """Minimal context should have no optimization components."""
        ctx = create_minimal_context(
            sandbox=MockSandbox(),
            llm=MockLLM(),
            checkpoint=MockCheckpoint(),
        )

        status = create_status(ctx)

        assert status.is_active is False
        assert status.components_enabled == []


class TestRiskTrustInteraction:
    """Test interaction between risk assessment and trust budget."""

    def test_high_risk_always_requires_verification(self) -> None:
        """HIGH risk actions should always require verification."""
        ctx = create_optimized_context(
            sandbox=MockSandbox(),
            llm=MockLLM(),
            checkpoint=MockCheckpoint(),
        )

        # Even with full trust, high risk requires verification
        assert ctx.trust_budget.remaining == 100  # Full trust

        action = Action(type=ActionType.COMMAND, content="rm -rf /tmp")
        risk = assess_risk(action)

        assert risk.level == RiskLevel.HIGH
        should_verify = ctx.trust_budget.should_verify(risk)
        assert should_verify is True

    def test_low_risk_can_skip_with_high_trust(self) -> None:
        """LOW risk actions can skip verification with high trust."""
        ctx = create_optimized_context(
            sandbox=MockSandbox(),
            llm=MockLLM(),
            checkpoint=MockCheckpoint(),
        )

        action = Action(type=ActionType.EDIT, content="import os")
        risk = assess_risk(action)

        assert risk.level == RiskLevel.LOW
        should_verify = ctx.trust_budget.should_verify(risk)
        assert should_verify is False  # Can skip

    def test_paranoid_context_always_verifies(self) -> None:
        """Paranoid context should always verify even low risk."""
        ctx = create_paranoid_context(
            sandbox=MockSandbox(),
            llm=MockLLM(),
            checkpoint=MockCheckpoint(),
        )

        # Trust is at floor
        assert ctx.trust_budget.remaining == ctx.trust_budget.floor

        action = Action(type=ActionType.EDIT, content="import os")
        risk = assess_risk(action)

        should_verify = ctx.trust_budget.should_verify(risk)
        assert should_verify is True  # Must verify at floor


class TestMetricsTracking:
    """Test metrics tracking through optimization flow."""

    def test_metrics_track_verifications_by_risk(self) -> None:
        """Metrics should track verifications by risk level."""
        ctx = create_optimized_context(
            sandbox=MockSandbox(),
            llm=MockLLM(),
            checkpoint=MockCheckpoint(),
        )

        # Simulate recording verifications
        ctx.metrics.record_verification("high")
        ctx.metrics.record_verification("high")
        ctx.metrics.record_verification("medium")
        ctx.metrics.record_verification("low")

        assert ctx.metrics.verifications_total == 4
        assert ctx.metrics.verifications_high_risk == 2
        assert ctx.metrics.verifications_medium_risk == 1
        assert ctx.metrics.verifications_low_risk == 1

    def test_metrics_in_status_summary(self) -> None:
        """Metrics data should appear in status summary."""
        ctx = create_optimized_context(
            sandbox=MockSandbox(),
            llm=MockLLM(),
            checkpoint=MockCheckpoint(),
            session_id="metrics-test",
        )

        ctx.metrics.record_llm_call("action", 1500)
        ctx.metrics.record_verification("medium")

        status = create_status(ctx)
        summary = status.summary()

        assert "metrics-test" in summary
        assert "LLM Calls: 1" in summary
        assert "Verifications: 1" in summary


class TestVerificationBatcherIntegration:
    """Test verification batcher in optimization flow."""

    def test_batcher_defers_low_risk(self) -> None:
        """Batcher should accept deferred low-risk verifications."""
        ctx = create_optimized_context(
            sandbox=MockSandbox(),
            llm=MockLLM(),
            checkpoint=MockCheckpoint(),
        )

        action = Action(type=ActionType.EDIT, content="import json")
        risk = assess_risk(action)

        # Defer to batcher
        ctx.verification_batcher.defer(action, "import added", "should have import")

        assert ctx.verification_batcher.pending_count == 1
        assert ctx.verification_batcher.has_pending() is True

    def test_batcher_flush_in_status(self) -> None:
        """Batcher pending status should show in status."""
        ctx = create_optimized_context(
            sandbox=MockSandbox(),
            llm=MockLLM(),
            checkpoint=MockCheckpoint(),
        )

        action = Action(type=ActionType.CREATE, content="create file")
        ctx.verification_batcher.defer(action, "file created", "file exists")

        status = create_status(ctx)
        summary = status.summary()

        assert "Pending: 1" in summary
        assert "DEFERRED" in summary


class TestComplexityRiskInteraction:
    """Test interaction between complexity and risk analysis."""

    def test_complex_task_analysis(self) -> None:
        """Complex tasks should be analyzed correctly."""
        complexity = analyze_complexity(
            what="Create API endpoint to fetch data from database and call external REST API",
            acceptance="Endpoint returns merged JSON from database and API",
        )

        # Complex task with external deps (database, API)
        assert complexity.has_external_deps is True
        assert complexity.score > 0.2

    def test_simple_task_low_complexity_low_risk(self) -> None:
        """Simple tasks should have low complexity and likely low risk."""
        complexity = analyze_complexity(
            what="Add import statement for json",
            acceptance="Import exists",
        )

        assert complexity.score < 0.5

        action = Action(type=ActionType.EDIT, content="import json")
        risk = assess_risk(action)

        assert risk.level == RiskLevel.LOW


class TestEfficiencyMetricsCalculation:
    """Test efficiency metrics calculation."""

    def test_skip_rate_calculation(self) -> None:
        """Verify skip rate calculation."""
        ctx = create_optimized_context(
            sandbox=MockSandbox(),
            llm=MockLLM(),
            checkpoint=MockCheckpoint(),
        )

        # Simulate mixed verification behavior
        ctx.trust_budget.verifications_performed = 7
        ctx.trust_budget.verifications_skipped = 3

        status = create_status(ctx)
        efficiency = status.get_efficiency_metrics()

        assert efficiency["verification_skip_rate"] == 30.0

    def test_failure_catch_rate(self) -> None:
        """Verify failure catch rate calculation."""
        ctx = create_optimized_context(
            sandbox=MockSandbox(),
            llm=MockLLM(),
            checkpoint=MockCheckpoint(),
        )

        ctx.trust_budget.failures_caught = 4
        ctx.trust_budget.failures_missed = 1

        status = create_status(ctx)
        efficiency = status.get_efficiency_metrics()

        assert efficiency["failure_catch_rate"] == 80.0


class TestTrustBudgetLifecycle:
    """Test trust budget changes over session lifecycle."""

    def test_trust_depletes_on_failure(self) -> None:
        """Trust should deplete when failures are missed."""
        ctx = create_optimized_context(
            sandbox=MockSandbox(),
            llm=MockLLM(),
            checkpoint=MockCheckpoint(),
        )

        initial = ctx.trust_budget.remaining
        ctx.trust_budget.deplete(20)

        assert ctx.trust_budget.remaining == initial - 20

    def test_trust_replenishes_on_success(self) -> None:
        """Trust should replenish on verified success."""
        ctx = create_optimized_context(
            sandbox=MockSandbox(),
            llm=MockLLM(),
            checkpoint=MockCheckpoint(),
        )

        ctx.trust_budget.remaining = 70
        ctx.trust_budget.replenish(10)

        assert ctx.trust_budget.remaining == 80

    def test_trust_mode_changes(self) -> None:
        """Trust mode should reflect current level."""
        ctx = create_optimized_context(
            sandbox=MockSandbox(),
            llm=MockLLM(),
            checkpoint=MockCheckpoint(),
        )

        # Start high
        assert ctx.trust_budget.is_high_trust is True

        # Deplete to low
        ctx.trust_budget.remaining = 40
        assert ctx.trust_budget.is_low_trust is True
        assert ctx.trust_budget.is_high_trust is False


class TestEndToEndScenario:
    """End-to-end scenario tests."""

    def test_typical_session_flow(self) -> None:
        """Simulate a typical RIVA session with optimizations."""
        ctx = create_optimized_context(
            sandbox=MockSandbox(),
            llm=MockLLM(),
            checkpoint=MockCheckpoint(),
            session_id="e2e-test",
        )

        # Simulate some work
        # 1. Analyze task complexity
        complexity = analyze_complexity(
            what="Add logging to the user service",
            acceptance="Logs appear when users are created",
        )

        # 2. Simulate multiple actions with different risk levels
        actions = [
            Action(type=ActionType.EDIT, content="import logging"),  # Low risk
            Action(type=ActionType.EDIT, content="logger = logging.getLogger()"),  # Low risk
            Action(type=ActionType.EDIT, content="logger.info('User created')"),  # Low risk
        ]

        for action in actions:
            risk = assess_risk(action)

            # Check if should verify
            should_verify = ctx.trust_budget.should_verify(risk)

            if should_verify:
                # Simulate verification
                ctx.metrics.record_verification(risk.level.value)
            else:
                # Defer to batcher
                ctx.verification_batcher.defer(action, "done", "expected")

        # 3. Check final status
        status = create_status(ctx)
        data = status.to_dict()

        assert data["is_active"] is True
        assert "metrics" in data
        assert "trust_budget" in data

        # Should have skipped some verifications (low risk + high trust)
        assert ctx.trust_budget.verifications_skipped > 0 or ctx.verification_batcher.pending_count > 0
