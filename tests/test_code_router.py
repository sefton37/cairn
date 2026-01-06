"""Tests for CodeModeRouter - request routing for Code Mode."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from reos.code_mode import CodeModeRouter, RequestType
from reos.play_fs import Act


@dataclass(frozen=True)
class MockAct:
    """Mock Act for testing without full play_fs dependency."""

    act_id: str = "test-act"
    title: str = "Test Act"
    active: bool = True
    notes: str = ""
    repo_path: str | None = None
    artifact_type: str | None = None
    code_config: dict | None = None


class TestRoutingDecision:
    """Tests for routing decision logic."""

    def test_no_active_act_returns_sysadmin(self) -> None:
        """Should return sysadmin mode when no active Act."""
        router = CodeModeRouter()
        decision = router.should_use_code_mode("write a function", None)

        assert decision.use_code_mode is False
        assert decision.request_type == RequestType.SYSADMIN
        assert "No active Act" in decision.reason

    def test_act_without_repo_returns_sysadmin(self) -> None:
        """Should return sysadmin mode when Act has no repo."""
        router = CodeModeRouter()
        act = MockAct(repo_path=None)
        decision = router.should_use_code_mode("write a function", act)  # type: ignore

        assert decision.use_code_mode is False
        assert decision.request_type == RequestType.SYSADMIN
        assert "no repository" in decision.reason.lower()

    def test_code_request_with_repo_returns_code_mode(self) -> None:
        """Should return code mode for code requests when Act has repo."""
        router = CodeModeRouter()
        act = MockAct(repo_path="/path/to/repo")
        decision = router.should_use_code_mode("write a function to parse JSON", act)  # type: ignore

        assert decision.use_code_mode is True
        assert decision.request_type == RequestType.CODE
        assert decision.confidence >= 0.7

    def test_clear_sysadmin_request_with_repo_returns_sysadmin(self) -> None:
        """Should return sysadmin mode for clear sysadmin requests even with repo."""
        router = CodeModeRouter()
        act = MockAct(repo_path="/path/to/repo")
        # Use a very clear sysadmin request with systemctl
        decision = router.should_use_code_mode("systemctl restart nginx", act)  # type: ignore

        assert decision.use_code_mode is False
        assert decision.request_type == RequestType.SYSADMIN


class TestCodePatternDetection:
    """Tests for code-related pattern detection."""

    @pytest.mark.parametrize(
        "user_request",
        [
            "write a function to calculate fibonacci",
            "create a new class for user authentication",
            "add a test for the login feature",
            "fix the bug in the payment module",
            "refactor the database connection code",
            "run pytest on the tests folder",
            "implement a REST API endpoint",
            "edit main.py to add logging",
            "debug the error in utils.py",
            "add type hints to the functions",
            "run the unit tests",
            "fix the failing test in test_user.py",
        ],
    )
    def test_detects_code_requests(self, user_request: str) -> None:
        """Should detect various code-related requests."""
        router = CodeModeRouter()
        act = MockAct(repo_path="/path/to/repo")
        decision = router.should_use_code_mode(user_request, act)  # type: ignore

        # Code requests should be routed to code mode (either CODE or AMBIGUOUS defaulting to code)
        assert decision.use_code_mode is True, f"Failed to route code request: {user_request}"


class TestSysadminPatternDetection:
    """Tests for sysadmin-related pattern detection."""

    @pytest.mark.parametrize(
        "user_request",
        [
            # Clear sysadmin patterns with explicit tool/command references
            "systemctl start postgresql",
            "check the disk usage",
            "df -h to show disk space",
            "check the network configuration",
            "configure the firewall rules",
            "journalctl -u nginx",
        ],
    )
    def test_detects_sysadmin_requests(self, user_request: str) -> None:
        """Should detect clear sysadmin-related requests."""
        router = CodeModeRouter()
        act = MockAct(repo_path="/path/to/repo")
        decision = router.should_use_code_mode(user_request, act)  # type: ignore

        assert decision.use_code_mode is False, f"Incorrectly routed sysadmin request: {user_request}"
        assert decision.request_type == RequestType.SYSADMIN


class TestAmbiguousRequests:
    """Tests for ambiguous request handling."""

    def test_ambiguous_request_defaults_to_code_with_repo(self) -> None:
        """Ambiguous requests should default to code mode when Act has repo."""
        router = CodeModeRouter()
        act = MockAct(repo_path="/path/to/repo")

        # This is ambiguous - could be asking about code or system
        decision = router.should_use_code_mode("what's happening?", act)  # type: ignore

        # With repo, ambiguous defaults to code mode
        assert decision.use_code_mode is True
        assert decision.request_type == RequestType.AMBIGUOUS
        assert decision.confidence < 0.7  # Lower confidence for ambiguous

    def test_greetings_are_ambiguous(self) -> None:
        """Simple greetings should be detected as ambiguous."""
        router = CodeModeRouter()
        act = MockAct(repo_path="/path/to/repo")

        decision = router.should_use_code_mode("hello", act)  # type: ignore

        assert decision.request_type == RequestType.AMBIGUOUS


class TestConfidenceScoring:
    """Tests for confidence score calculation."""

    def test_multiple_code_patterns_increase_confidence(self) -> None:
        """Multiple code pattern matches should increase confidence."""
        router = CodeModeRouter()
        act = MockAct(repo_path="/path/to/repo")

        # Request with multiple code patterns
        decision = router.should_use_code_mode(
            "write a function and add tests and run pytest", act  # type: ignore
        )

        assert decision.confidence > 0.8

    def test_single_pattern_has_moderate_confidence(self) -> None:
        """Single pattern match should have moderate confidence."""
        router = CodeModeRouter()
        act = MockAct(repo_path="/path/to/repo")

        decision = router.should_use_code_mode("edit the file", act)  # type: ignore

        assert 0.6 <= decision.confidence <= 0.9


class TestWithRealAct:
    """Tests using real Act dataclass from play_fs."""

    def test_with_real_act_no_repo(self) -> None:
        """Should work with real Act dataclass without repo."""
        router = CodeModeRouter()
        act = Act(act_id="test", title="Test", active=True)
        decision = router.should_use_code_mode("write code", act)

        assert decision.use_code_mode is False

    def test_with_real_act_with_repo(self, temp_git_repo: Path) -> None:
        """Should work with real Act dataclass with repo."""
        router = CodeModeRouter()
        act = Act(
            act_id="test",
            title="Test",
            active=True,
            repo_path=str(temp_git_repo),
            artifact_type="python",
        )
        decision = router.should_use_code_mode("write a function", act)

        assert decision.use_code_mode is True
