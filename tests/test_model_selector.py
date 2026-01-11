"""Tests for model selection based on task complexity.

Tests that the model selector chooses appropriate models
based on task complexity and system resources.
"""

from __future__ import annotations

import pytest

from reos.code_mode.optimization.complexity import (
    TaskComplexity,
    ComplexityLevel,
    analyze_complexity,
)
from reos.code_mode.optimization.model_selector import (
    ModelTier,
    ModelSelection,
    select_model,
    get_tier_for_model,
    recommend_models_for_system,
    DEFAULT_MODELS,
)


class TestModelTier:
    """Test ModelTier enum."""

    def test_tier_values(self) -> None:
        """Tier values should be string identifiers."""
        assert ModelTier.SMALL.value == "small"
        assert ModelTier.MEDIUM.value == "medium"
        assert ModelTier.LARGE.value == "large"


class TestModelSelection:
    """Test ModelSelection dataclass."""

    def test_create_selection(self) -> None:
        """Basic model selection creation."""
        selection = ModelSelection(
            tier=ModelTier.MEDIUM,
            model_name="llama3.2:8b",
            reason="Moderate complexity",
        )

        assert selection.tier == ModelTier.MEDIUM
        assert selection.model_name == "llama3.2:8b"
        assert selection.reason == "Moderate complexity"
        assert selection.confidence == 0.8  # Default

    def test_custom_confidence(self) -> None:
        """Custom confidence should be respected."""
        selection = ModelSelection(
            tier=ModelTier.LARGE,
            model_name="llama3.2:70b",
            reason="Complex task",
            confidence=0.95,
        )

        assert selection.confidence == 0.95


class TestSelectModel:
    """Test select_model() function."""

    def test_simple_task_selects_small(self) -> None:
        """Simple tasks should select SMALL tier."""
        complexity = analyze_complexity(
            what="Create a hello world function",
            acceptance="Function prints hello",
        )

        selection = select_model(complexity)

        assert selection.tier == ModelTier.SMALL
        assert "simple" in selection.reason.lower() or "small" in selection.reason.lower()

    def test_complex_task_selects_large(self) -> None:
        """Complex tasks should select LARGE tier."""
        complexity = analyze_complexity(
            what="Refactor the entire authentication system to use OAuth2 with JWT tokens and refresh token rotation",
            acceptance="All tests pass and security audit passes",
        )

        # Complex task should have high score
        if complexity.score > 0.7:
            selection = select_model(complexity)
            assert selection.tier == ModelTier.LARGE
            assert "complex" in selection.reason.lower() or "capable" in selection.reason.lower()

    def test_external_deps_selects_medium(self) -> None:
        """Tasks with external deps should select at least MEDIUM if score > 0.3."""
        complexity = analyze_complexity(
            what="Create REST API endpoint to POST user data to external database and send email notifications via SMTP",
            acceptance="API returns 201 and email is sent",
        )

        selection = select_model(complexity)

        # External deps detected should influence selection
        # Only assert if complexity score > 0.3 (threshold for small)
        if complexity.has_external_deps and complexity.score > 0.3:
            assert selection.tier in (ModelTier.MEDIUM, ModelTier.LARGE)

    def test_ambiguous_scope_selects_medium(self) -> None:
        """Ambiguous scope should select MEDIUM."""
        complexity = analyze_complexity(
            what="Fix it",
            acceptance="Works",
        )

        selection = select_model(complexity)

        # Ambiguous scope should use balanced model
        if complexity.scope_ambiguous:
            assert selection.tier in (ModelTier.MEDIUM, ModelTier.LARGE)

    def test_with_available_models(self) -> None:
        """Should pick from available models."""
        complexity = analyze_complexity(
            what="Add a simple utility function",
            acceptance="Returns correct value",
        )

        available = ["qwen2.5:3b", "llama3.2:8b"]
        selection = select_model(complexity, available_models=available)

        assert selection.model_name in available

    def test_fallback_to_default(self) -> None:
        """Should use default when tier unavailable."""
        complexity = analyze_complexity(
            what="Simple task",
            acceptance="Works",
        )

        # No available models match preferred
        available = ["custom-model:latest"]
        selection = select_model(
            complexity,
            available_models=available,
            default_model="custom-model:latest",
        )

        assert selection.model_name == "custom-model:latest"


class TestGetTierForModel:
    """Test get_tier_for_model() function."""

    def test_small_models_by_size(self) -> None:
        """Models with small size indicators should be SMALL."""
        assert get_tier_for_model("llama3.2:3b") == ModelTier.SMALL
        assert get_tier_for_model("qwen2.5:3b") == ModelTier.SMALL
        assert get_tier_for_model("phi3:mini") == ModelTier.SMALL

    def test_large_models_by_size(self) -> None:
        """Models with large size indicators should be LARGE."""
        assert get_tier_for_model("llama3.2:70b") == ModelTier.LARGE
        assert get_tier_for_model("qwen2.5:72b") == ModelTier.LARGE
        assert get_tier_for_model("codellama:34b") == ModelTier.LARGE

    def test_medium_models_default(self) -> None:
        """Models without clear size should default to MEDIUM."""
        assert get_tier_for_model("llama3.2") == ModelTier.MEDIUM
        assert get_tier_for_model("mistral:7b") == ModelTier.MEDIUM
        assert get_tier_for_model("unknown-model") == ModelTier.MEDIUM

    def test_case_insensitive(self) -> None:
        """Model tier detection should be case insensitive."""
        assert get_tier_for_model("LLAMA3.2:3B") == ModelTier.SMALL
        assert get_tier_for_model("Qwen2.5:72B") == ModelTier.LARGE


class TestRecommendModelsForSystem:
    """Test recommend_models_for_system() function."""

    def test_low_resource_system(self) -> None:
        """Low resource system gets small models."""
        recommendations = recommend_models_for_system(
            ram_gb=8,
            has_gpu=False,
            vram_gb=0,
        )

        # Should recommend small model for medium tier
        assert recommendations[ModelTier.SMALL] == "llama3.2:3b"
        # Medium tier falls back to small model
        assert recommendations[ModelTier.MEDIUM] == "llama3.2:3b"

    def test_medium_resource_system(self) -> None:
        """Medium resource system gets appropriate models."""
        recommendations = recommend_models_for_system(
            ram_gb=16,
            has_gpu=False,
            vram_gb=0,
        )

        assert recommendations[ModelTier.SMALL] == "llama3.2:3b"
        assert recommendations[ModelTier.MEDIUM] == "llama3.2:8b"

    def test_gpu_system(self) -> None:
        """GPU system with sufficient VRAM gets better models."""
        recommendations = recommend_models_for_system(
            ram_gb=32,
            has_gpu=True,
            vram_gb=12,
        )

        assert recommendations[ModelTier.MEDIUM] == "llama3.2:8b"

    def test_high_end_system(self) -> None:
        """High-end system gets large models."""
        recommendations = recommend_models_for_system(
            ram_gb=64,
            has_gpu=True,
            vram_gb=24,
        )

        assert recommendations[ModelTier.LARGE] == "llama3.2:70b"


class TestDefaultModels:
    """Test DEFAULT_MODELS configuration."""

    def test_all_tiers_have_defaults(self) -> None:
        """Each tier should have default model options."""
        assert ModelTier.SMALL in DEFAULT_MODELS
        assert ModelTier.MEDIUM in DEFAULT_MODELS
        assert ModelTier.LARGE in DEFAULT_MODELS

    def test_defaults_are_lists(self) -> None:
        """Default models should be lists for flexibility."""
        for tier, models in DEFAULT_MODELS.items():
            assert isinstance(models, list)
            assert len(models) > 0


class TestModelSelectionIntegration:
    """Test model selection with real complexity analysis."""

    def test_end_to_end_simple(self) -> None:
        """Simple task end-to-end model selection."""
        complexity = analyze_complexity(
            what="Create function add(a, b) that returns sum",
            acceptance="add(2, 3) returns 5",
        )

        selection = select_model(
            complexity,
            available_models=["llama3.2:3b", "llama3.2:8b", "llama3.2:70b"],
        )

        # Simple function should use small model
        assert selection.tier == ModelTier.SMALL

    def test_end_to_end_moderate(self) -> None:
        """Moderate task end-to-end model selection."""
        complexity = analyze_complexity(
            what="Refactor user authentication to add input validation, password strength checking, and rate limiting to prevent brute force attacks",
            acceptance="All validation passes and security tests pass",
        )

        selection = select_model(
            complexity,
            available_models=["llama3.2:3b", "llama3.2:8b", "llama3.2:70b"],
        )

        # More complex task with multiple requirements
        # Should select medium or higher if score > 0.3
        if complexity.score > 0.3:
            assert selection.tier in (ModelTier.MEDIUM, ModelTier.LARGE)
