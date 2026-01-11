"""Tests for optimization factory functions.

Tests that factory functions correctly configure WorkContext
with appropriate optimization components.
"""

from __future__ import annotations

import pytest

from reos.code_mode.optimization.factory import (
    create_optimized_context,
    create_minimal_context,
    create_metrics_only_context,
    create_high_trust_context,
    create_paranoid_context,
)


class MockSandbox:
    """Mock sandbox for testing."""
    pass


class MockLLM:
    """Mock LLM provider for testing."""
    pass


class MockCheckpoint:
    """Mock checkpoint for testing."""
    pass


class TestCreateOptimizedContext:
    """Test create_optimized_context factory."""

    def test_creates_with_all_components(self) -> None:
        """Should create context with all optimization components."""
        ctx = create_optimized_context(
            sandbox=MockSandbox(),
            llm=MockLLM(),
            checkpoint=MockCheckpoint(),
        )

        assert ctx.metrics is not None
        assert ctx.trust_budget is not None
        assert ctx.verification_batcher is not None

    def test_auto_generates_session_id(self) -> None:
        """Should auto-generate session ID when not provided."""
        ctx = create_optimized_context(
            sandbox=MockSandbox(),
            llm=MockLLM(),
            checkpoint=MockCheckpoint(),
        )

        assert ctx.metrics is not None
        assert ctx.metrics.session_id is not None
        assert len(ctx.metrics.session_id) == 8

    def test_uses_provided_session_id(self) -> None:
        """Should use provided session ID."""
        ctx = create_optimized_context(
            sandbox=MockSandbox(),
            llm=MockLLM(),
            checkpoint=MockCheckpoint(),
            session_id="custom-session",
        )

        assert ctx.metrics.session_id == "custom-session"

    def test_disable_metrics(self) -> None:
        """Should allow disabling metrics."""
        ctx = create_optimized_context(
            sandbox=MockSandbox(),
            llm=MockLLM(),
            checkpoint=MockCheckpoint(),
            enable_metrics=False,
        )

        assert ctx.metrics is None
        assert ctx.trust_budget is not None

    def test_disable_trust_budget(self) -> None:
        """Should allow disabling trust budget."""
        ctx = create_optimized_context(
            sandbox=MockSandbox(),
            llm=MockLLM(),
            checkpoint=MockCheckpoint(),
            enable_trust_budget=False,
        )

        assert ctx.metrics is not None
        assert ctx.trust_budget is None

    def test_disable_verification_batcher(self) -> None:
        """Should allow disabling verification batcher."""
        ctx = create_optimized_context(
            sandbox=MockSandbox(),
            llm=MockLLM(),
            checkpoint=MockCheckpoint(),
            enable_verification_batcher=False,
        )

        assert ctx.metrics is not None
        assert ctx.verification_batcher is None

    def test_custom_trust_settings(self) -> None:
        """Should apply custom trust budget settings."""
        ctx = create_optimized_context(
            sandbox=MockSandbox(),
            llm=MockLLM(),
            checkpoint=MockCheckpoint(),
            initial_trust=50,
            trust_floor=10,
        )

        assert ctx.trust_budget.initial == 50
        assert ctx.trust_budget.remaining == 50
        assert ctx.trust_budget.floor == 10

    def test_custom_limits(self) -> None:
        """Should apply custom context limits."""
        ctx = create_optimized_context(
            sandbox=MockSandbox(),
            llm=MockLLM(),
            checkpoint=MockCheckpoint(),
            max_cycles_per_intention=10,
            max_depth=20,
        )

        assert ctx.max_cycles_per_intention == 10
        assert ctx.max_depth == 20

    def test_passes_llm_to_batcher(self) -> None:
        """Should pass LLM to verification batcher."""
        llm = MockLLM()
        ctx = create_optimized_context(
            sandbox=MockSandbox(),
            llm=llm,
            checkpoint=MockCheckpoint(),
        )

        assert ctx.verification_batcher.llm is llm


class TestCreateMinimalContext:
    """Test create_minimal_context factory."""

    def test_creates_without_optimizations(self) -> None:
        """Should create context without any optimization components."""
        ctx = create_minimal_context(
            sandbox=MockSandbox(),
            llm=MockLLM(),
            checkpoint=MockCheckpoint(),
        )

        assert ctx.metrics is None
        assert ctx.trust_budget is None
        assert ctx.verification_batcher is None

    def test_accepts_session_logger(self) -> None:
        """Should accept session logger."""
        class MockLogger:
            pass

        ctx = create_minimal_context(
            sandbox=MockSandbox(),
            llm=MockLLM(),
            checkpoint=MockCheckpoint(),
            session_logger=MockLogger(),
        )

        assert ctx.session_logger is not None


class TestCreateMetricsOnlyContext:
    """Test create_metrics_only_context factory."""

    def test_creates_with_metrics_only(self) -> None:
        """Should create context with only metrics enabled."""
        ctx = create_metrics_only_context(
            sandbox=MockSandbox(),
            llm=MockLLM(),
            checkpoint=MockCheckpoint(),
        )

        assert ctx.metrics is not None
        assert ctx.trust_budget is None
        assert ctx.verification_batcher is None

    def test_uses_session_id(self) -> None:
        """Should use provided session ID."""
        ctx = create_metrics_only_context(
            sandbox=MockSandbox(),
            llm=MockLLM(),
            checkpoint=MockCheckpoint(),
            session_id="metrics-test",
        )

        assert ctx.metrics.session_id == "metrics-test"


class TestCreateHighTrustContext:
    """Test create_high_trust_context factory."""

    def test_creates_with_high_trust(self) -> None:
        """Should create context with high initial trust."""
        ctx = create_high_trust_context(
            sandbox=MockSandbox(),
            llm=MockLLM(),
            checkpoint=MockCheckpoint(),
        )

        assert ctx.trust_budget is not None
        assert ctx.trust_budget.initial == 100
        assert ctx.trust_budget.floor == 10  # Lower floor

    def test_all_components_enabled(self) -> None:
        """Should have all optimization components enabled."""
        ctx = create_high_trust_context(
            sandbox=MockSandbox(),
            llm=MockLLM(),
            checkpoint=MockCheckpoint(),
        )

        assert ctx.metrics is not None
        assert ctx.trust_budget is not None
        assert ctx.verification_batcher is not None


class TestCreateParanoidContext:
    """Test create_paranoid_context factory."""

    def test_creates_with_low_trust(self) -> None:
        """Should create context that starts at floor."""
        ctx = create_paranoid_context(
            sandbox=MockSandbox(),
            llm=MockLLM(),
            checkpoint=MockCheckpoint(),
        )

        assert ctx.trust_budget is not None
        assert ctx.trust_budget.initial == 20
        assert ctx.trust_budget.remaining == 20
        assert ctx.trust_budget.floor == 20

    def test_no_verification_batcher(self) -> None:
        """Should not use verification batcher (no batching)."""
        ctx = create_paranoid_context(
            sandbox=MockSandbox(),
            llm=MockLLM(),
            checkpoint=MockCheckpoint(),
        )

        assert ctx.verification_batcher is None

    def test_metrics_enabled(self) -> None:
        """Should still collect metrics."""
        ctx = create_paranoid_context(
            sandbox=MockSandbox(),
            llm=MockLLM(),
            checkpoint=MockCheckpoint(),
        )

        assert ctx.metrics is not None


class TestFactoryWithNoneLLM:
    """Test factories handle None LLM correctly."""

    def test_optimized_with_none_llm(self) -> None:
        """Should work with None LLM."""
        ctx = create_optimized_context(
            sandbox=MockSandbox(),
            llm=None,
            checkpoint=MockCheckpoint(),
        )

        assert ctx.llm is None
        assert ctx.verification_batcher is not None
        assert ctx.verification_batcher.llm is None

    def test_minimal_with_none_llm(self) -> None:
        """Should work with None LLM."""
        ctx = create_minimal_context(
            sandbox=MockSandbox(),
            llm=None,
            checkpoint=MockCheckpoint(),
        )

        assert ctx.llm is None
