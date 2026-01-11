"""Tests for trust budget integration with RIVA.

Tests that the trust budget system properly manages verification
decisions based on action risk and session history.
"""

from __future__ import annotations

import pytest

from reos.code_mode.intention import Action, ActionType
from reos.code_mode.optimization.risk import (
    ActionRisk,
    RiskLevel,
    assess_risk,
)
from reos.code_mode.optimization.trust import (
    TrustBudget,
    create_trust_budget,
)


class TestTrustBudgetCreation:
    """Test trust budget creation and initialization."""

    def test_create_default_budget(self) -> None:
        """Default budget should start at 100 with floor of 20."""
        budget = create_trust_budget()

        assert budget.initial == 100
        assert budget.remaining == 100
        assert budget.floor == 20
        assert budget.verifications_skipped == 0
        assert budget.verifications_performed == 0

    def test_create_custom_budget(self) -> None:
        """Custom budget parameters should be respected."""
        budget = create_trust_budget(initial=50, floor=10)

        assert budget.initial == 50
        assert budget.remaining == 50
        assert budget.floor == 10

    def test_trust_level_percentage(self) -> None:
        """Trust level should be calculated as percentage."""
        budget = create_trust_budget(initial=100)
        assert budget.trust_level == 1.0

        budget.remaining = 50
        assert budget.trust_level == 0.5

        budget.remaining = 25
        assert budget.trust_level == 0.25


class TestTrustBudgetVerificationDecisions:
    """Test should_verify() decision making."""

    def test_high_risk_always_verify(self) -> None:
        """HIGH risk actions should always be verified."""
        budget = create_trust_budget(initial=100)

        action = Action(type=ActionType.COMMAND, content="rm -rf /tmp/test")
        risk = assess_risk(action)

        assert risk.level == RiskLevel.HIGH
        assert budget.should_verify(risk) is True
        assert budget.verifications_performed == 1
        assert budget.verifications_skipped == 0

    def test_high_risk_verify_even_at_max_trust(self) -> None:
        """HIGH risk should verify even with maximum trust."""
        budget = create_trust_budget(initial=100)

        # Create high risk action
        risk = ActionRisk(
            level=RiskLevel.HIGH,
            factors=["security_password"],
            requires_verification=True,
            can_batch=False,
        )

        assert budget.should_verify(risk) is True

    def test_low_risk_can_skip_with_high_trust(self) -> None:
        """LOW risk actions can skip verification with high trust (>70)."""
        budget = create_trust_budget(initial=100)

        risk = ActionRisk(
            level=RiskLevel.LOW,
            factors=["boilerplate_import"],
            requires_verification=False,
            can_batch=True,
        )

        # With trust at 100 (>70), low risk can skip
        assert budget.should_verify(risk) is False
        assert budget.verifications_skipped == 1

    def test_low_risk_must_verify_with_low_trust(self) -> None:
        """LOW risk actions must verify when trust is low (<=70)."""
        budget = create_trust_budget(initial=100)
        budget.remaining = 50  # Below threshold

        risk = ActionRisk(
            level=RiskLevel.LOW,
            factors=["read_only_search"],
            requires_verification=False,
            can_batch=True,
        )

        # With trust at 50 (<=70), must verify
        assert budget.should_verify(risk) is True
        assert budget.verifications_performed == 1

    def test_medium_risk_can_skip_with_very_high_trust(self) -> None:
        """MEDIUM risk can skip verification only with very high trust (>85)."""
        budget = create_trust_budget(initial=100)

        risk = ActionRisk(
            level=RiskLevel.MEDIUM,
            factors=["action_type_edit"],
            requires_verification=True,
            can_batch=True,
        )

        # With trust at 100 (>85), medium risk can skip
        assert budget.should_verify(risk) is False
        assert budget.verifications_skipped == 1

    def test_medium_risk_must_verify_below_threshold(self) -> None:
        """MEDIUM risk must verify when trust is below 85."""
        budget = create_trust_budget(initial=100)
        budget.remaining = 80  # Below 85 threshold

        risk = ActionRisk(
            level=RiskLevel.MEDIUM,
            factors=["action_type_edit"],
            requires_verification=True,
            can_batch=True,
        )

        assert budget.should_verify(risk) is True

    def test_below_floor_always_verify(self) -> None:
        """When at floor, all actions must be verified."""
        budget = create_trust_budget(initial=100, floor=20)
        budget.remaining = 20  # At floor

        # Even low risk must verify
        low_risk = ActionRisk(
            level=RiskLevel.LOW,
            factors=["boilerplate_import"],
            requires_verification=False,
            can_batch=True,
        )

        assert budget.should_verify(low_risk) is True


class TestTrustBudgetReplenishment:
    """Test trust replenishment on success."""

    def test_replenish_increases_trust(self) -> None:
        """Replenish should increase remaining trust."""
        budget = create_trust_budget(initial=100)
        budget.remaining = 80

        budget.replenish(10)

        assert budget.remaining == 90

    def test_replenish_caps_at_initial(self) -> None:
        """Replenish should not exceed initial budget."""
        budget = create_trust_budget(initial=100)
        budget.remaining = 95

        budget.replenish(20)

        assert budget.remaining == 100  # Capped at initial

    def test_default_replenish_amount(self) -> None:
        """Default replenishment is 10."""
        budget = create_trust_budget(initial=100)
        budget.remaining = 70

        budget.replenish()

        assert budget.remaining == 80


class TestTrustBudgetDepletion:
    """Test trust depletion on failure."""

    def test_deplete_decreases_trust(self) -> None:
        """Deplete should decrease remaining trust."""
        budget = create_trust_budget(initial=100)

        budget.deplete(20)

        assert budget.remaining == 80
        assert budget.failures_missed == 1

    def test_deplete_respects_floor(self) -> None:
        """Deplete should not go below floor."""
        budget = create_trust_budget(initial=100, floor=20)
        budget.remaining = 30

        budget.deplete(50)

        assert budget.remaining == 20  # At floor, not below

    def test_default_deplete_amount(self) -> None:
        """Default depletion is 20."""
        budget = create_trust_budget(initial=100)

        budget.deplete()

        assert budget.remaining == 80


class TestTrustBudgetFailureCaught:
    """Test failure caught tracking."""

    def test_record_failure_caught(self) -> None:
        """Recording failure caught should increment counter."""
        budget = create_trust_budget(initial=100)
        budget.remaining = 80

        budget.record_failure_caught()

        assert budget.failures_caught == 1
        # Should also get small replenishment (verification worked)
        assert budget.remaining == 85  # +5 replenishment

    def test_multiple_failures_caught(self) -> None:
        """Multiple failures caught should accumulate."""
        budget = create_trust_budget(initial=100)
        budget.remaining = 70

        budget.record_failure_caught()
        budget.record_failure_caught()
        budget.record_failure_caught()

        assert budget.failures_caught == 3


class TestTrustBudgetModes:
    """Test trust mode detection."""

    def test_is_low_trust(self) -> None:
        """Low trust mode when remaining <= 50."""
        budget = create_trust_budget(initial=100)

        budget.remaining = 60
        assert budget.is_low_trust is False

        budget.remaining = 50
        assert budget.is_low_trust is True

        budget.remaining = 30
        assert budget.is_low_trust is True

    def test_is_high_trust(self) -> None:
        """High trust mode when remaining >= 80."""
        budget = create_trust_budget(initial=100)

        budget.remaining = 70
        assert budget.is_high_trust is False

        budget.remaining = 80
        assert budget.is_high_trust is True

        budget.remaining = 100
        assert budget.is_high_trust is True


class TestTrustBudgetSerialization:
    """Test trust budget serialization."""

    def test_summary(self) -> None:
        """Summary should include key metrics."""
        budget = create_trust_budget(initial=100)
        budget.verifications_performed = 5
        budget.verifications_skipped = 2
        budget.failures_caught = 1
        budget.remaining = 85

        summary = budget.summary()

        assert "85/100" in summary
        assert "verified=5" in summary
        assert "skipped=2" in summary
        assert "caught=1" in summary

    def test_to_dict(self) -> None:
        """to_dict should include all relevant fields."""
        budget = create_trust_budget(initial=100)
        budget.verifications_performed = 3
        budget.verifications_skipped = 1
        budget.remaining = 90

        data = budget.to_dict()

        assert data["initial"] == 100
        assert data["remaining"] == 90
        assert data["floor"] == 20
        assert data["trust_level"] == 0.9
        assert data["statistics"]["verifications_performed"] == 3
        assert data["statistics"]["verifications_skipped"] == 1


class TestTrustBudgetIntegrationScenario:
    """Test realistic integration scenarios."""

    def test_session_with_mixed_actions(self) -> None:
        """Simulate a session with mixed risk actions."""
        budget = create_trust_budget(initial=100)

        # Low risk action - should skip (trust > 70)
        low_risk = ActionRisk(
            level=RiskLevel.LOW,
            factors=["boilerplate_import"],
            requires_verification=False,
            can_batch=True,
        )
        assert budget.should_verify(low_risk) is False

        # Medium risk action - should skip (trust > 85)
        medium_risk = ActionRisk(
            level=RiskLevel.MEDIUM,
            factors=["action_type_edit"],
            requires_verification=True,
            can_batch=True,
        )
        # Trust depleted slightly by skipping low risk
        # Still above 85, so medium can skip too
        should_verify_medium = budget.should_verify(medium_risk)
        # After first skip, trust is ~97, so medium can still skip

        # High risk action - always verify
        high_risk = ActionRisk(
            level=RiskLevel.HIGH,
            factors=["security_password"],
            requires_verification=True,
            can_batch=False,
        )
        assert budget.should_verify(high_risk) is True

        # Verify we tracked correctly
        assert budget.verifications_performed >= 1  # At least high risk
        assert budget.verifications_skipped >= 1  # At least low risk

    def test_trust_recovery_after_failures(self) -> None:
        """Trust should recover after successful verifications."""
        budget = create_trust_budget(initial=100)

        # Simulate multiple failures
        budget.deplete(20)
        budget.deplete(20)
        budget.deplete(20)

        assert budget.remaining == 40

        # Now simulate successful verified actions
        budget.replenish(10)
        budget.replenish(10)
        budget.replenish(10)

        assert budget.remaining == 70

    def test_progressive_trust_degradation(self) -> None:
        """Trust should progressively require more verification."""
        budget = create_trust_budget(initial=100)

        low_risk = ActionRisk(
            level=RiskLevel.LOW,
            factors=["read_only_search"],
            requires_verification=False,
            can_batch=True,
        )

        # Initially can skip
        skip_count = 0
        for _ in range(20):
            if not budget.should_verify(low_risk):
                skip_count += 1

        # After many skips, budget depletes and eventually must verify
        assert skip_count < 20  # Can't skip forever
        assert budget.verifications_performed > 0  # Had to verify eventually
