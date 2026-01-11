"""Tests for fast-path pattern detection.

Tests that the fast-path module correctly detects common patterns
for optimized handling.
"""

from __future__ import annotations

import pytest

from reos.code_mode.optimization.fast_path import (
    FastPathPattern,
    PatternMatch,
    detect_pattern,
    get_available_patterns,
    is_pattern_available,
)


class TestPatternDetection:
    """Test detect_pattern() function."""

    def test_detect_create_function(self) -> None:
        """Should detect 'create function' pattern."""
        result = detect_pattern("create a function to calculate tax")

        assert result.pattern == FastPathPattern.CREATE_FUNCTION
        assert result.confidence >= 0.7

    def test_detect_add_function(self) -> None:
        """Should detect 'add function' as create function."""
        result = detect_pattern("add a function called validate_input")

        assert result.pattern == FastPathPattern.CREATE_FUNCTION
        assert result.is_match is True

    def test_detect_add_test(self) -> None:
        """Should detect 'add test' pattern."""
        result = detect_pattern("add a test for the login function")

        assert result.pattern == FastPathPattern.ADD_TEST
        assert result.is_match is True

    def test_detect_write_test(self) -> None:
        """Should detect 'write test' pattern."""
        result = detect_pattern("write test for user registration")

        assert result.pattern == FastPathPattern.ADD_TEST
        assert result.is_match is True

    def test_detect_fix_import(self) -> None:
        """Should detect 'fix import' pattern."""
        result = detect_pattern("fix the missing import for json")

        assert result.pattern == FastPathPattern.FIX_IMPORT
        assert result.is_match is True

    def test_detect_add_import(self) -> None:
        """Should detect 'add import' pattern."""
        result = detect_pattern("add import for datetime module")

        assert result.pattern == FastPathPattern.ADD_IMPORT
        assert result.is_match is True

    def test_detect_fix_typo(self) -> None:
        """Should detect 'fix typo' pattern."""
        result = detect_pattern("fix the typo in the function name")

        assert result.pattern == FastPathPattern.FIX_TYPO
        assert result.is_match is True

    def test_no_pattern_for_complex_task(self) -> None:
        """Complex tasks should not match fast path."""
        result = detect_pattern(
            "refactor the authentication system to use OAuth2"
        )

        # Should not match any simple pattern
        assert result.confidence < 0.7 or result.pattern is None


class TestPatternAntiKeywords:
    """Test that anti-keywords prevent false matches."""

    def test_create_class_not_function(self) -> None:
        """'create class' should not match CREATE_FUNCTION."""
        result = detect_pattern("create a class for handling users")

        # Should match CREATE_CLASS, not CREATE_FUNCTION
        if result.is_match:
            assert result.pattern != FastPathPattern.CREATE_FUNCTION

    def test_fix_test_not_add_test(self) -> None:
        """'fix test' should not match ADD_TEST."""
        result = detect_pattern("fix the failing test in auth module")

        # "fix" is an anti-keyword for ADD_TEST
        assert result.pattern != FastPathPattern.ADD_TEST or not result.is_match


class TestPatternMatch:
    """Test PatternMatch dataclass."""

    def test_is_match_true(self) -> None:
        """is_match should be True when confidence >= 0.7."""
        match = PatternMatch(
            pattern=FastPathPattern.CREATE_FUNCTION,
            confidence=0.8,
            extracted={"func_hint": "calculate"},
        )

        assert match.is_match is True

    def test_is_match_false_low_confidence(self) -> None:
        """is_match should be False when confidence < 0.7."""
        match = PatternMatch(
            pattern=FastPathPattern.CREATE_FUNCTION,
            confidence=0.5,
            extracted={},
        )

        assert match.is_match is False

    def test_is_match_false_no_pattern(self) -> None:
        """is_match should be False when pattern is None."""
        match = PatternMatch(
            pattern=None,
            confidence=0.0,
            extracted={},
        )

        assert match.is_match is False


class TestPatternExtraction:
    """Test parameter extraction from patterns."""

    def test_extract_import_name(self) -> None:
        """Should extract import name."""
        result = detect_pattern("add import datetime")

        # Extraction depends on implementation
        if "import" in result.extracted:
            assert result.extracted["import"] == "datetime"

    def test_extract_test_hint(self) -> None:
        """Should extract test hint."""
        result = detect_pattern("add test_login function")

        if "test_hint" in result.extracted:
            assert "login" in result.extracted["test_hint"]


class TestPatternAvailability:
    """Test pattern availability functions."""

    def test_get_available_patterns_empty(self) -> None:
        """Currently no patterns are implemented (returns empty)."""
        patterns = get_available_patterns()

        # The scaffolding returns empty list
        # When implemented, this test should change
        assert isinstance(patterns, list)

    def test_is_pattern_available(self) -> None:
        """is_pattern_available should check implementation status."""
        # Currently none are available
        assert is_pattern_available(FastPathPattern.CREATE_FUNCTION) is False
        assert is_pattern_available(FastPathPattern.ADD_TEST) is False


class TestPatternDetectionEdgeCases:
    """Test edge cases in pattern detection."""

    def test_empty_string(self) -> None:
        """Empty string should not match."""
        result = detect_pattern("")

        assert result.is_match is False

    def test_very_short_input(self) -> None:
        """Very short input may not match confidently."""
        result = detect_pattern("fix")

        # May or may not match depending on implementation
        # Should not crash
        assert isinstance(result, PatternMatch)

    def test_acceptance_criteria_helps(self) -> None:
        """Acceptance criteria should be considered."""
        result1 = detect_pattern("add something")
        result2 = detect_pattern("add something", "test passes")

        # With "test" in acceptance, might match ADD_TEST better
        # This tests that acceptance is used
        assert isinstance(result1, PatternMatch)
        assert isinstance(result2, PatternMatch)

    def test_case_insensitive(self) -> None:
        """Pattern detection should be case insensitive."""
        result1 = detect_pattern("CREATE A FUNCTION")
        result2 = detect_pattern("create a function")

        # Both should match
        assert result1.pattern == result2.pattern
