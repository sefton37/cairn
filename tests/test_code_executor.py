"""Tests for CodeExecutor - the main execution loop."""

from __future__ import annotations

from pathlib import Path

import pytest

from reos.code_mode import (
    CodeExecutor,
    CodeSandbox,
    ExecutionState,
    ExecutionResult,
    LoopStatus,
    PerspectiveManager,
    Phase,
    ANALYST,
    ARCHITECT,
    ENGINEER,
    CRITIC,
)
from reos.play_fs import Act


class TestPerspectives:
    """Tests for perspective management."""

    def test_shift_to_phase(self) -> None:
        """Should shift to phase perspective."""
        manager = PerspectiveManager(ollama=None)

        perspective = manager.shift_to(Phase.INTENT)

        assert perspective == ANALYST
        assert manager.current_perspective == ANALYST

    def test_get_perspective_without_shift(self) -> None:
        """Should get perspective without changing current."""
        manager = PerspectiveManager(ollama=None)
        manager.shift_to(Phase.INTENT)

        perspective = manager.get_perspective(Phase.BUILD)

        assert perspective == ENGINEER
        assert manager.current_perspective == ANALYST  # Unchanged

    def test_phase_perspectives_mapping(self) -> None:
        """Should have correct phase-perspective mapping."""
        manager = PerspectiveManager(ollama=None)

        assert manager.get_perspective(Phase.INTENT) == ANALYST
        assert manager.get_perspective(Phase.CONTRACT) == ARCHITECT
        assert manager.get_perspective(Phase.BUILD) == ENGINEER
        assert manager.get_perspective(Phase.VERIFY) == CRITIC

    def test_perspective_has_system_prompt(self) -> None:
        """Each perspective should have a system prompt."""
        perspectives = [ANALYST, ARCHITECT, ENGINEER, CRITIC]

        for p in perspectives:
            assert p.system_prompt
            assert len(p.system_prompt) > 100


class TestCodeExecutor:
    """Tests for the main executor."""

    def test_init(self, temp_git_repo: Path) -> None:
        """Should initialize executor."""
        sandbox = CodeSandbox(temp_git_repo)
        executor = CodeExecutor(sandbox, ollama=None)

        assert executor.sandbox == sandbox

    def test_execute_creates_state(self, temp_git_repo: Path) -> None:
        """Execute should create execution state."""
        sandbox = CodeSandbox(temp_git_repo)
        executor = CodeExecutor(sandbox, ollama=None)
        act = Act(
            act_id="test",
            title="Test",
            active=True,
            repo_path=str(temp_git_repo),
        )

        result = executor.execute(
            "add a hello function",
            act,
            max_iterations=1,  # Limit for testing
        )

        assert isinstance(result, ExecutionResult)
        assert isinstance(result.state, ExecutionState)

    def test_execute_discovers_intent(self, temp_git_repo: Path) -> None:
        """Execute should discover intent."""
        sandbox = CodeSandbox(temp_git_repo)
        executor = CodeExecutor(sandbox, ollama=None)
        act = Act(
            act_id="test",
            title="Test",
            active=True,
            repo_path=str(temp_git_repo),
        )

        result = executor.execute(
            "add a hello function",
            act,
            max_iterations=1,
        )

        assert result.state.intent is not None

    def test_execute_builds_contract(self, temp_git_repo: Path) -> None:
        """Execute should build contract."""
        sandbox = CodeSandbox(temp_git_repo)
        executor = CodeExecutor(sandbox, ollama=None)
        act = Act(
            act_id="test",
            title="Test",
            active=True,
            repo_path=str(temp_git_repo),
        )

        result = executor.execute(
            "add a function",
            act,
            max_iterations=1,
        )

        assert result.state.current_contract is not None
        assert len(result.state.contracts) > 0

    def test_execute_respects_max_iterations(self, temp_git_repo: Path) -> None:
        """Execute should stop at max iterations."""
        sandbox = CodeSandbox(temp_git_repo)
        executor = CodeExecutor(sandbox, ollama=None)
        act = Act(
            act_id="test",
            title="Test",
            active=True,
            repo_path=str(temp_git_repo),
        )

        result = executor.execute(
            "add a complex feature",
            act,
            max_iterations=2,
        )

        assert result.state.current_iteration <= 2

    def test_execute_tracks_iterations(self, temp_git_repo: Path) -> None:
        """Execute should track iteration history."""
        sandbox = CodeSandbox(temp_git_repo)
        executor = CodeExecutor(sandbox, ollama=None)
        act = Act(
            act_id="test",
            title="Test",
            active=True,
            repo_path=str(temp_git_repo),
        )

        result = executor.execute(
            "add a function",
            act,
            max_iterations=2,
        )

        assert len(result.state.iterations) > 0
        for iteration in result.state.iterations:
            assert iteration.started_at is not None


class TestExecutionState:
    """Tests for execution state management."""

    def test_initial_status(self) -> None:
        """Initial status should be pending."""
        state = ExecutionState(
            session_id="test",
            prompt="test prompt",
        )

        assert state.status == LoopStatus.PENDING

    def test_has_timestamps(self) -> None:
        """Should have started_at timestamp."""
        state = ExecutionState(
            session_id="test",
            prompt="test prompt",
        )

        assert state.started_at is not None


class TestExecutionResult:
    """Tests for execution results."""

    def test_result_message(self, temp_git_repo: Path) -> None:
        """Result should have message."""
        sandbox = CodeSandbox(temp_git_repo)
        executor = CodeExecutor(sandbox, ollama=None)
        act = Act(
            act_id="test",
            title="Test",
            active=True,
            repo_path=str(temp_git_repo),
        )

        result = executor.execute(
            "add a function",
            act,
            max_iterations=1,
        )

        assert result.message
        assert len(result.message) > 0

    def test_result_has_iteration_count(self, temp_git_repo: Path) -> None:
        """Result should have iteration count."""
        sandbox = CodeSandbox(temp_git_repo)
        executor = CodeExecutor(sandbox, ollama=None)
        act = Act(
            act_id="test",
            title="Test",
            active=True,
            repo_path=str(temp_git_repo),
        )

        result = executor.execute(
            "add a function",
            act,
            max_iterations=2,
        )

        assert result.total_iterations >= 0


class TestPreviewPlan:
    """Tests for plan preview generation."""

    def test_preview_includes_intent(self, temp_git_repo: Path) -> None:
        """Preview should include intent summary."""
        sandbox = CodeSandbox(temp_git_repo)
        executor = CodeExecutor(sandbox, ollama=None)
        act = Act(
            act_id="test",
            title="Test",
            active=True,
            repo_path=str(temp_git_repo),
        )

        result = executor.execute(
            "add a function",
            act,
            max_iterations=1,
        )

        preview = executor.preview_plan(result.state)

        assert "Intent" in preview or "Plan" in preview

    def test_preview_includes_contract(self, temp_git_repo: Path) -> None:
        """Preview should include contract summary."""
        sandbox = CodeSandbox(temp_git_repo)
        executor = CodeExecutor(sandbox, ollama=None)
        act = Act(
            act_id="test",
            title="Test",
            active=True,
            repo_path=str(temp_git_repo),
        )

        result = executor.execute(
            "add a function",
            act,
            max_iterations=1,
        )

        preview = executor.preview_plan(result.state)

        assert "Contract" in preview or "Criteria" in preview
