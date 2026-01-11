"""Tests for complexity analyzer integration with RIVA.

Tests that the complexity analyzer is properly integrated into
can_verify_directly() and makes smarter decomposition decisions.
"""

from __future__ import annotations

import pytest

from reos.code_mode.optimization.complexity import (
    TaskComplexity,
    ComplexityLevel,
    analyze_complexity,
)


class TestComplexityAnalyzer:
    """Test the complexity analyzer module."""

    def test_simple_task_low_complexity(self) -> None:
        """Simple, well-defined tasks should have low complexity."""
        result = analyze_complexity(
            what="Create a hello world function",
            acceptance="Function returns 'Hello World'",
        )

        assert result.score < 0.4
        assert result.level in (ComplexityLevel.TRIVIAL, ComplexityLevel.SIMPLE)
        assert result.should_decompose is False
        assert result.confidence >= 0.7

    def test_compound_task_high_complexity(self) -> None:
        """Tasks with compound structure should have higher complexity."""
        result = analyze_complexity(
            what="Create a user registration system and then add email verification and also implement password reset",
            acceptance="All features work",
        )

        assert result.has_compound_structure is True
        assert result.should_decompose is True

    def test_multi_file_task(self) -> None:
        """Tasks involving multiple files should score higher."""
        result = analyze_complexity(
            what="Refactor auth.py, users.py, and permissions.py to use new base class",
            acceptance="All files updated",
        )

        assert result.estimated_files >= 3
        assert result.score > 0.3

    def test_ambiguous_scope(self) -> None:
        """Tasks with ambiguous scope should recommend decomposition."""
        result = analyze_complexity(
            what="Fix it",
            acceptance="Works properly",
        )

        assert result.scope_ambiguous is True
        assert result.should_decompose is True

    def test_external_deps_detection(self) -> None:
        """Tasks with external dependencies should be detected."""
        result = analyze_complexity(
            what="Add API endpoint to fetch user data from database",
            acceptance="Endpoint returns JSON",
        )

        assert result.has_external_deps is True

    def test_single_function_simple(self) -> None:
        """Single function creation should be simple."""
        result = analyze_complexity(
            what="Add a factorial function to math_utils.py",
            acceptance="factorial(5) returns 120",
        )

        assert result.estimated_functions == 1
        assert result.score < 0.5

    def test_modification_vs_creation(self) -> None:
        """Modifying existing code adds complexity."""
        create_result = analyze_complexity(
            what="Create a new logger module",
            acceptance="Logger works",
        )

        modify_result = analyze_complexity(
            what="Refactor the existing logger to use structured logging",
            acceptance="Logger works",
        )

        assert modify_result.modifies_existing is True
        assert create_result.modifies_existing is False
        # Modification should score slightly higher
        assert modify_result.score >= create_result.score

    def test_test_requirement_detection(self) -> None:
        """Tasks requiring tests should be detected."""
        result = analyze_complexity(
            what="Add input validation",
            acceptance="All tests pass",
        )

        assert result.requires_tests is True

    def test_confidence_levels(self) -> None:
        """Confidence should vary with clarity of task."""
        clear_result = analyze_complexity(
            what="Create function add(a, b) that returns sum",
            acceptance="add(2, 3) returns 5",
        )

        vague_result = analyze_complexity(
            what="Make it better",
            acceptance="Improved",
        )

        # Clear task should have higher confidence
        assert clear_result.confidence > vague_result.confidence

    def test_to_dict_serialization(self) -> None:
        """TaskComplexity should serialize properly."""
        result = analyze_complexity(
            what="Create hello function",
            acceptance="Returns hello",
        )

        data = result.to_dict()

        assert "level" in data
        assert "score" in data
        assert "factors" in data
        assert "decision" in data
        assert data["decision"]["should_decompose"] == result.should_decompose


class TestComplexityEdgeCases:
    """Test edge cases in complexity analysis."""

    def test_empty_acceptance(self) -> None:
        """Should handle empty acceptance criteria."""
        result = analyze_complexity(
            what="Create a function",
            acceptance="",
        )

        # Empty acceptance is ambiguous
        assert result.scope_ambiguous is True

    def test_very_short_task(self) -> None:
        """Very short tasks might be ambiguous."""
        result = analyze_complexity(
            what="Fix bug",
            acceptance="Works",
        )

        assert result.scope_ambiguous is True

    def test_numbered_list_compound(self) -> None:
        """Numbered lists should be detected as compound."""
        result = analyze_complexity(
            what="1. Create model 2. Add routes 3. Write tests",
            acceptance="All done",
        )

        assert result.has_compound_structure is True

    def test_file_extension_detection(self) -> None:
        """Should detect file mentions."""
        result = analyze_complexity(
            what="Update config.py and utils.py",
            acceptance="Files updated",
        )

        assert result.estimated_files >= 2
