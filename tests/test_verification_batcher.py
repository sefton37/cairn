"""Tests for batch verification system.

Tests that the verification batcher correctly defers and batches
verifications for reduced LLM calls.
"""

from __future__ import annotations

import pytest

from reos.code_mode.intention import Action, ActionType
from reos.code_mode.optimization.verification import (
    DeferredVerification,
    BatchVerificationResult,
    VerificationBatcher,
)


class TestDeferredVerification:
    """Test DeferredVerification dataclass."""

    def test_create_deferred(self) -> None:
        """Basic deferred verification creation."""
        action = Action(type=ActionType.CREATE, content="create file.py")
        deferred = DeferredVerification(
            action=action,
            result="File created successfully",
            expected="file.py exists",
        )

        assert deferred.action == action
        assert deferred.result == "File created successfully"
        assert deferred.expected == "file.py exists"


class TestBatchVerificationResult:
    """Test BatchVerificationResult dataclass."""

    def test_all_passed(self) -> None:
        """Result with all verifications passed."""
        action = Action(type=ActionType.CREATE, content="test")
        v1 = DeferredVerification(action, "ok", "should work")
        v2 = DeferredVerification(action, "ok", "should also work")

        result = BatchVerificationResult(
            success=True,
            results=[(v1, True), (v2, True)],
            failures=[],
        )

        assert result.success is True
        assert result.passed_count == 2
        assert result.failed_count == 0

    def test_some_failed(self) -> None:
        """Result with some verifications failed."""
        action = Action(type=ActionType.CREATE, content="test")
        v1 = DeferredVerification(action, "ok", "should work")
        v2 = DeferredVerification(action, "error", "should fail")

        result = BatchVerificationResult(
            success=False,
            results=[(v1, True), (v2, False)],
            failures=[v2],
        )

        assert result.success is False
        assert result.passed_count == 1
        assert result.failed_count == 1

    def test_empty_result(self) -> None:
        """Empty batch result."""
        result = BatchVerificationResult(
            success=True,
            results=[],
            failures=[],
        )

        assert result.success is True
        assert result.passed_count == 0
        assert result.failed_count == 0


class TestVerificationBatcher:
    """Test VerificationBatcher class."""

    def test_create_batcher(self) -> None:
        """Basic batcher creation."""
        batcher = VerificationBatcher()

        assert batcher.pending_count == 0
        assert batcher.has_pending() is False

    def test_defer_verification(self) -> None:
        """Defer adds to pending count."""
        batcher = VerificationBatcher()
        action = Action(type=ActionType.CREATE, content="test")

        batcher.defer(action, "result", "expected")

        assert batcher.pending_count == 1
        assert batcher.has_pending() is True

    def test_defer_multiple(self) -> None:
        """Multiple deferrals accumulate."""
        batcher = VerificationBatcher()
        action = Action(type=ActionType.CREATE, content="test")

        batcher.defer(action, "result1", "expected1")
        batcher.defer(action, "result2", "expected2")
        batcher.defer(action, "result3", "expected3")

        assert batcher.pending_count == 3

    def test_flush_empty(self) -> None:
        """Flushing empty batcher succeeds."""
        batcher = VerificationBatcher()

        result = batcher.flush()

        assert result.success is True
        assert len(result.results) == 0

    def test_flush_clears_pending(self) -> None:
        """Flush clears pending verifications."""
        batcher = VerificationBatcher()
        action = Action(type=ActionType.CREATE, content="test")

        batcher.defer(action, "result", "expected")
        assert batcher.pending_count == 1

        batcher.flush()
        assert batcher.pending_count == 0

    def test_clear(self) -> None:
        """Clear removes pending without running."""
        batcher = VerificationBatcher()
        action = Action(type=ActionType.CREATE, content="test")

        batcher.defer(action, "result1", "expected1")
        batcher.defer(action, "result2", "expected2")
        assert batcher.pending_count == 2

        batcher.clear()
        assert batcher.pending_count == 0


class TestHeuristicVerification:
    """Test heuristic verification without LLM."""

    def test_success_indicator_passes(self) -> None:
        """Results with success indicators should pass."""
        batcher = VerificationBatcher(llm=None)
        action = Action(type=ActionType.CREATE, content="create file.py")

        batcher.defer(action, "File created successfully", "file should exist")
        result = batcher.flush()

        assert result.success is True

    def test_error_indicator_fails(self) -> None:
        """Results with error indicators should fail."""
        batcher = VerificationBatcher(llm=None)
        action = Action(type=ActionType.CREATE, content="create file.py")

        batcher.defer(action, "Error: file not found", "file should exist")
        result = batcher.flush()

        assert result.success is False
        assert result.failed_count == 1

    def test_exception_indicator_fails(self) -> None:
        """Results with exception indicators should fail."""
        batcher = VerificationBatcher(llm=None)
        action = Action(type=ActionType.COMMAND, content="run script")

        batcher.defer(action, "Traceback (most recent call last)...", "should complete")
        result = batcher.flush()

        assert result.success is False

    def test_permission_denied_fails(self) -> None:
        """Permission denied should fail."""
        batcher = VerificationBatcher(llm=None)
        action = Action(type=ActionType.COMMAND, content="chmod")

        batcher.defer(action, "Permission denied: /etc/passwd", "should modify")
        result = batcher.flush()

        assert result.success is False

    def test_created_indicator_passes(self) -> None:
        """Created indicator should pass."""
        batcher = VerificationBatcher(llm=None)
        action = Action(type=ActionType.CREATE, content="create class")

        batcher.defer(action, "class MyClass created in models.py", "class should exist")
        result = batcher.flush()

        assert result.success is True

    def test_done_indicator_passes(self) -> None:
        """Done indicator should pass."""
        batcher = VerificationBatcher(llm=None)
        action = Action(type=ActionType.EDIT, content="update function")

        batcher.defer(action, "Done. Function updated.", "function should be updated")
        result = batcher.flush()

        assert result.success is True

    def test_mixed_results(self) -> None:
        """Mixed success/failure results."""
        batcher = VerificationBatcher(llm=None)
        action = Action(type=ActionType.CREATE, content="test")

        batcher.defer(action, "File created successfully", "file should exist")
        batcher.defer(action, "Error: permission denied", "should have access")
        batcher.defer(action, "Done adding function", "function should exist")

        result = batcher.flush()

        assert result.success is False  # At least one failure
        assert result.passed_count == 2
        assert result.failed_count == 1


class TestHeuristicExpectedMatch:
    """Test heuristic matching of expected outcomes."""

    def test_expected_words_match(self) -> None:
        """Result containing expected words should pass."""
        batcher = VerificationBatcher(llm=None)
        action = Action(type=ActionType.CREATE, content="add function")

        batcher.defer(
            action,
            "Added new function calculate_total to utils.py",
            "function calculate_total added",
        )
        result = batcher.flush()

        assert result.success is True

    def test_unclear_result_fails(self) -> None:
        """Unclear results should fail (safer)."""
        batcher = VerificationBatcher(llm=None)
        action = Action(type=ActionType.EDIT, content="modify")

        batcher.defer(
            action,
            "xyz 123 abc",  # No clear indicators
            "should update configuration",
        )
        result = batcher.flush()

        assert result.success is False


class TestBatchPromptBuilding:
    """Test batch prompt construction."""

    def test_build_batch_prompt(self) -> None:
        """Batch prompt includes all deferred items."""
        batcher = VerificationBatcher(llm=None)
        action1 = Action(type=ActionType.CREATE, content="create file1")
        action2 = Action(type=ActionType.EDIT, content="edit file2")

        batcher.defer(action1, "result1", "expected1")
        batcher.defer(action2, "result2", "expected2")

        prompt = batcher._build_batch_prompt()

        assert "Item 1:" in prompt
        assert "Item 2:" in prompt
        assert "expected1" in prompt
        assert "expected2" in prompt
        assert "create" in prompt
        assert "edit" in prompt


class TestVerificationBatcherIntegration:
    """Integration tests for verification batcher."""

    def test_typical_workflow(self) -> None:
        """Test typical defer-defer-flush workflow."""
        batcher = VerificationBatcher(llm=None)

        # Simulate executing multiple low-risk actions
        actions = [
            (Action(type=ActionType.CREATE, content="import os"), "import added", "import statement"),
            (Action(type=ActionType.EDIT, content="add docstring"), "docstring added successfully", "docstring"),
            (Action(type=ActionType.CREATE, content="create function"), "function created", "new function"),
        ]

        for action, result, expected in actions:
            batcher.defer(action, result, expected)

        assert batcher.pending_count == 3

        # Flush at intention boundary
        result = batcher.flush()

        assert result.success is True
        assert result.passed_count == 3
        assert batcher.pending_count == 0

    def test_flush_on_high_risk(self) -> None:
        """Simulate flushing before high-risk action."""
        batcher = VerificationBatcher(llm=None)

        # Defer some low-risk actions
        action = Action(type=ActionType.CREATE, content="add import")
        batcher.defer(action, "import added successfully", "import exists")
        batcher.defer(action, "function created", "function exists")

        # Before high-risk action, flush
        result = batcher.flush()
        assert result.success is True

        # Now safe to execute high-risk action
        assert batcher.pending_count == 0

    def test_error_recovery(self) -> None:
        """Test recovery when batch verification fails."""
        batcher = VerificationBatcher(llm=None)

        # Mix of success and failure
        action = Action(type=ActionType.CREATE, content="test")
        batcher.defer(action, "File created", "file exists")
        batcher.defer(action, "Error: disk full", "data written")

        result = batcher.flush()

        # Should report failure
        assert result.success is False

        # Should identify which failed
        assert len(result.failures) == 1
        assert "disk full" in result.failures[0].result
