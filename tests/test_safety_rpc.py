"""Unit tests for the safety/ RPC handler functions (src/cairn/rpc_handlers/safety.py).

Each handler is tested with mocked security module dependencies so tests only verify:
- Clamping logic for every bounded setter
- Correct delegation to rate_limiter.configure()
- Module-level attribute mutation and db.set_state() calls for set_command_length
- Return-value shape matches the documented contract

No real DB, no real rate limiter, no real security module state.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# =============================================================================
# Helpers
# =============================================================================


def _mock_db() -> MagicMock:
    """Return a dummy Database object."""
    return MagicMock()


def _make_rate_limiter(limits: dict | None = None) -> MagicMock:
    """Return a MagicMock that stands in for CommandRateLimiter."""
    rl = MagicMock()
    rl._limits = limits if limits is not None else {}
    return rl


def _make_limit_config(name: str = "cmd", max_requests: int = 10, window_seconds: float = 60.0):
    """Return a MagicMock that stands in for a RateLimitConfig."""
    cfg = MagicMock()
    cfg.name = name
    cfg.max_requests = max_requests
    cfg.window_seconds = window_seconds
    return cfg


# =============================================================================
# handle_safety_settings
# =============================================================================


class TestHandleSafetySettings:
    """handle_safety_settings reads rate_limiter._limits and security constants."""

    def test_returns_expected_keys(self) -> None:
        from cairn.rpc_handlers.safety import handle_safety_settings

        rl = _make_rate_limiter()
        with patch("cairn.rpc_handlers.safety.get_rate_limiter", return_value=rl):
            result = handle_safety_settings(_mock_db())

        assert "rate_limits" in result
        assert "max_command_length" in result
        assert "max_service_name_length" in result
        assert "max_container_id_length" in result
        assert "max_package_name_length" in result
        assert "dangerous_pattern_count" in result
        assert "injection_pattern_count" in result

    def test_rate_limits_reflects_limiter_contents(self) -> None:
        from cairn.rpc_handlers.safety import handle_safety_settings

        cfg = _make_limit_config(name="execute", max_requests=5, window_seconds=30.0)
        rl = _make_rate_limiter(limits={"execute": cfg})

        with patch("cairn.rpc_handlers.safety.get_rate_limiter", return_value=rl):
            result = handle_safety_settings(_mock_db())

        assert result["rate_limits"]["execute"]["max_requests"] == 5
        assert result["rate_limits"]["execute"]["window_seconds"] == 30.0
        assert result["rate_limits"]["execute"]["name"] == "execute"

    def test_pattern_counts_are_non_negative_integers(self) -> None:
        from cairn.rpc_handlers.safety import handle_safety_settings

        rl = _make_rate_limiter()
        with patch("cairn.rpc_handlers.safety.get_rate_limiter", return_value=rl):
            result = handle_safety_settings(_mock_db())

        assert isinstance(result["dangerous_pattern_count"], int)
        assert result["dangerous_pattern_count"] >= 0
        assert isinstance(result["injection_pattern_count"], int)
        assert result["injection_pattern_count"] >= 0

    def test_empty_limits_returns_empty_rate_limits_dict(self) -> None:
        from cairn.rpc_handlers.safety import handle_safety_settings

        rl = _make_rate_limiter(limits={})
        with patch("cairn.rpc_handlers.safety.get_rate_limiter", return_value=rl):
            result = handle_safety_settings(_mock_db())

        assert result["rate_limits"] == {}


# =============================================================================
# handle_safety_set_rate_limit
# =============================================================================


class TestHandleSafetySetRateLimit:
    """handle_safety_set_rate_limit clamps max_requests (1-100) and window_seconds (10-600)."""

    def test_within_bounds_value_passes_through(self) -> None:
        from cairn.rpc_handlers.safety import handle_safety_set_rate_limit

        rl = _make_rate_limiter()
        with patch("cairn.rpc_handlers.safety.get_rate_limiter", return_value=rl):
            result = handle_safety_set_rate_limit(
                _mock_db(), category="execute", max_requests=50, window_seconds=300
            )

        assert result["success"] is True
        assert result["category"] == "execute"
        assert result["max_requests"] == 50
        assert result["window_seconds"] == 300

    def test_max_requests_below_minimum_clamped_to_1(self) -> None:
        from cairn.rpc_handlers.safety import handle_safety_set_rate_limit

        rl = _make_rate_limiter()
        with patch("cairn.rpc_handlers.safety.get_rate_limiter", return_value=rl):
            result = handle_safety_set_rate_limit(
                _mock_db(), category="execute", max_requests=0, window_seconds=60
            )

        assert result["max_requests"] == 1

    def test_max_requests_above_maximum_clamped_to_100(self) -> None:
        from cairn.rpc_handlers.safety import handle_safety_set_rate_limit

        rl = _make_rate_limiter()
        with patch("cairn.rpc_handlers.safety.get_rate_limiter", return_value=rl):
            result = handle_safety_set_rate_limit(
                _mock_db(), category="execute", max_requests=999, window_seconds=60
            )

        assert result["max_requests"] == 100

    def test_window_seconds_below_minimum_clamped_to_10(self) -> None:
        from cairn.rpc_handlers.safety import handle_safety_set_rate_limit

        rl = _make_rate_limiter()
        with patch("cairn.rpc_handlers.safety.get_rate_limiter", return_value=rl):
            result = handle_safety_set_rate_limit(
                _mock_db(), category="execute", max_requests=10, window_seconds=5
            )

        assert result["window_seconds"] == 10

    def test_window_seconds_above_maximum_clamped_to_600(self) -> None:
        from cairn.rpc_handlers.safety import handle_safety_set_rate_limit

        rl = _make_rate_limiter()
        with patch("cairn.rpc_handlers.safety.get_rate_limiter", return_value=rl):
            result = handle_safety_set_rate_limit(
                _mock_db(), category="execute", max_requests=10, window_seconds=9999
            )

        assert result["window_seconds"] == 600

    def test_calls_rate_limiter_configure_with_clamped_values(self) -> None:
        from cairn.rpc_handlers.safety import handle_safety_set_rate_limit

        rl = _make_rate_limiter()
        with patch("cairn.rpc_handlers.safety.get_rate_limiter", return_value=rl):
            handle_safety_set_rate_limit(
                _mock_db(), category="execute", max_requests=0, window_seconds=9999
            )

        rl.configure.assert_called_once_with("execute", 1, 600)


# =============================================================================
# handle_safety_set_sudo_limit
# =============================================================================


class TestHandleSafetySetSudoLimit:
    """handle_safety_set_sudo_limit clamps max_escalations to 1-20, no side effects."""

    def test_within_bounds_value_passes_through(self) -> None:
        from cairn.rpc_handlers.safety import handle_safety_set_sudo_limit

        result = handle_safety_set_sudo_limit(_mock_db(), max_escalations=10)

        assert result["success"] is True
        assert result["max_escalations"] == 10

    def test_value_below_minimum_clamped_to_1(self) -> None:
        from cairn.rpc_handlers.safety import handle_safety_set_sudo_limit

        result = handle_safety_set_sudo_limit(_mock_db(), max_escalations=0)

        assert result["max_escalations"] == 1

    def test_value_above_maximum_clamped_to_20(self) -> None:
        from cairn.rpc_handlers.safety import handle_safety_set_sudo_limit

        result = handle_safety_set_sudo_limit(_mock_db(), max_escalations=100)

        assert result["max_escalations"] == 20

    def test_negative_value_clamped_to_1(self) -> None:
        from cairn.rpc_handlers.safety import handle_safety_set_sudo_limit

        result = handle_safety_set_sudo_limit(_mock_db(), max_escalations=-5)

        assert result["max_escalations"] == 1


# =============================================================================
# handle_safety_set_command_length
# =============================================================================


class TestHandleSafetySetCommandLength:
    """handle_safety_set_command_length clamps to 512-32768, mutates security module, calls db."""

    def test_within_bounds_value_passes_through(self) -> None:
        from cairn.rpc_handlers.safety import handle_safety_set_command_length
        import cairn.security as security

        original = security.MAX_COMMAND_LEN
        try:
            db = _mock_db()
            result = handle_safety_set_command_length(db, max_length=4096)

            assert result["success"] is True
            assert result["max_length"] == 4096
        finally:
            security.MAX_COMMAND_LEN = original

    def test_value_below_minimum_clamped_to_512(self) -> None:
        from cairn.rpc_handlers.safety import handle_safety_set_command_length
        import cairn.security as security

        original = security.MAX_COMMAND_LEN
        try:
            result = handle_safety_set_command_length(_mock_db(), max_length=100)
            assert result["max_length"] == 512
        finally:
            security.MAX_COMMAND_LEN = original

    def test_value_above_maximum_clamped_to_32768(self) -> None:
        from cairn.rpc_handlers.safety import handle_safety_set_command_length
        import cairn.security as security

        original = security.MAX_COMMAND_LEN
        try:
            result = handle_safety_set_command_length(_mock_db(), max_length=999999)
            assert result["max_length"] == 32768
        finally:
            security.MAX_COMMAND_LEN = original

    def test_updates_security_module_attribute(self) -> None:
        from cairn.rpc_handlers.safety import handle_safety_set_command_length
        import cairn.security as security

        original = security.MAX_COMMAND_LEN
        try:
            handle_safety_set_command_length(_mock_db(), max_length=8192)
            assert security.MAX_COMMAND_LEN == 8192
        finally:
            security.MAX_COMMAND_LEN = original

    def test_calls_db_set_state_with_clamped_value(self) -> None:
        from cairn.rpc_handlers.safety import handle_safety_set_command_length
        import cairn.security as security

        original = security.MAX_COMMAND_LEN
        try:
            db = _mock_db()
            handle_safety_set_command_length(db, max_length=100)
            db.set_state.assert_called_once_with(key="safety_command_length", value="512")
        finally:
            security.MAX_COMMAND_LEN = original


# =============================================================================
# handle_safety_set_max_iterations
# =============================================================================


class TestHandleSafetySetMaxIterations:
    """handle_safety_set_max_iterations clamps max_iterations to 3-100, no side effects."""

    def test_within_bounds_value_passes_through(self) -> None:
        from cairn.rpc_handlers.safety import handle_safety_set_max_iterations

        result = handle_safety_set_max_iterations(_mock_db(), max_iterations=50)

        assert result["success"] is True
        assert result["max_iterations"] == 50

    def test_value_below_minimum_clamped_to_3(self) -> None:
        from cairn.rpc_handlers.safety import handle_safety_set_max_iterations

        result = handle_safety_set_max_iterations(_mock_db(), max_iterations=1)

        assert result["max_iterations"] == 3

    def test_value_above_maximum_clamped_to_100(self) -> None:
        from cairn.rpc_handlers.safety import handle_safety_set_max_iterations

        result = handle_safety_set_max_iterations(_mock_db(), max_iterations=500)

        assert result["max_iterations"] == 100

    def test_exact_boundary_values_not_clamped(self) -> None:
        from cairn.rpc_handlers.safety import handle_safety_set_max_iterations

        result_min = handle_safety_set_max_iterations(_mock_db(), max_iterations=3)
        result_max = handle_safety_set_max_iterations(_mock_db(), max_iterations=100)

        assert result_min["max_iterations"] == 3
        assert result_max["max_iterations"] == 100


# =============================================================================
# handle_safety_set_wall_clock_timeout
# =============================================================================


class TestHandleSafetySetWallClockTimeout:
    """handle_safety_set_wall_clock_timeout clamps timeout_seconds to 60-3600, no side effects."""

    def test_within_bounds_value_passes_through(self) -> None:
        from cairn.rpc_handlers.safety import handle_safety_set_wall_clock_timeout

        result = handle_safety_set_wall_clock_timeout(_mock_db(), timeout_seconds=1800)

        assert result["success"] is True
        assert result["timeout_seconds"] == 1800

    def test_value_below_minimum_clamped_to_60(self) -> None:
        from cairn.rpc_handlers.safety import handle_safety_set_wall_clock_timeout

        result = handle_safety_set_wall_clock_timeout(_mock_db(), timeout_seconds=10)

        assert result["timeout_seconds"] == 60

    def test_value_above_maximum_clamped_to_3600(self) -> None:
        from cairn.rpc_handlers.safety import handle_safety_set_wall_clock_timeout

        result = handle_safety_set_wall_clock_timeout(_mock_db(), timeout_seconds=7200)

        assert result["timeout_seconds"] == 3600

    def test_exact_boundary_values_not_clamped(self) -> None:
        from cairn.rpc_handlers.safety import handle_safety_set_wall_clock_timeout

        result_min = handle_safety_set_wall_clock_timeout(_mock_db(), timeout_seconds=60)
        result_max = handle_safety_set_wall_clock_timeout(_mock_db(), timeout_seconds=3600)

        assert result_min["timeout_seconds"] == 60
        assert result_max["timeout_seconds"] == 3600
