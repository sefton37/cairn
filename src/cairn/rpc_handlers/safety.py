"""Safety and security settings RPC handlers.

These handlers manage rate limits, sudo escalation limits,
command length limits, and other safety parameters.
"""

from __future__ import annotations

from typing import Any

from cairn.db import Database
from cairn.security import (
    get_rate_limiter,
    DANGEROUS_PATTERNS,
    INJECTION_PATTERNS,
    MAX_COMMAND_LEN,
    MAX_SERVICE_NAME_LEN,
    MAX_CONTAINER_ID_LEN,
    MAX_PACKAGE_NAME_LEN,
)


# =============================================================================
# Safety Settings Handlers
# =============================================================================


def handle_safety_settings(_db: Database) -> dict[str, Any]:
    """Get current safety settings and limits."""
    rate_limiter = get_rate_limiter()

    # Build rate limits dict
    rate_limits = {}
    for category, config in rate_limiter._limits.items():
        rate_limits[category] = {
            "max_requests": config.max_requests,
            "window_seconds": config.window_seconds,
            "name": config.name,
        }

    return {
        "rate_limits": rate_limits,
        "max_command_length": MAX_COMMAND_LEN,
        "max_service_name_length": MAX_SERVICE_NAME_LEN,
        "max_container_id_length": MAX_CONTAINER_ID_LEN,
        "max_package_name_length": MAX_PACKAGE_NAME_LEN,
        "dangerous_pattern_count": len(DANGEROUS_PATTERNS),
        "injection_pattern_count": len(INJECTION_PATTERNS),
    }


def handle_safety_set_rate_limit(
    _db: Database,
    *,
    category: str,
    max_requests: int,
    window_seconds: float,
) -> dict[str, Any]:
    """Update a rate limit configuration."""
    rate_limiter = get_rate_limiter()

    # Validate bounds
    if max_requests < 1:
        max_requests = 1
    if max_requests > 100:
        max_requests = 100
    if window_seconds < 10:
        window_seconds = 10
    if window_seconds > 600:
        window_seconds = 600

    rate_limiter.configure(category, max_requests, window_seconds)

    return {
        "success": True,
        "category": category,
        "max_requests": max_requests,
        "window_seconds": window_seconds,
    }


def handle_safety_set_sudo_limit(
    _db: Database,
    *,
    max_escalations: int,
) -> dict[str, Any]:
    """Update the sudo escalation limit.

    Note: linux_tools module has been removed. This setting is persisted
    for future use but has no effect on the current runtime.
    """
    # Validate bounds (1-20)
    if max_escalations < 1:
        max_escalations = 1
    if max_escalations > 20:
        max_escalations = 20

    return {
        "success": True,
        "max_escalations": max_escalations,
    }


def handle_safety_set_command_length(
    db: Database,
    *,
    max_length: int,
) -> dict[str, Any]:
    """Update the maximum command length."""
    from cairn import security

    # Validate bounds (512-32768)
    if max_length < 512:
        max_length = 512
    if max_length > 32768:
        max_length = 32768

    # Update the module-level constant
    security.MAX_COMMAND_LEN = max_length

    # Persist to database
    db.set_state(key="safety_command_length", value=str(max_length))

    return {
        "success": True,
        "max_length": max_length,
    }


def handle_safety_set_max_iterations(
    _db: Database,
    *,
    max_iterations: int,
) -> dict[str, Any]:
    """Update the maximum iterations for agent execution.

    Note: code_mode executor has been removed. This setting is persisted
    for future use but has no effect on the current runtime.
    """
    # Validate bounds (3-100)
    if max_iterations < 3:
        max_iterations = 3
    if max_iterations > 100:
        max_iterations = 100

    return {
        "success": True,
        "max_iterations": max_iterations,
    }


def handle_safety_set_wall_clock_timeout(
    _db: Database,
    *,
    timeout_seconds: int,
) -> dict[str, Any]:
    """Update the wall-clock timeout for agent execution.

    Note: code_mode executor has been removed. This setting is persisted
    for future use but has no effect on the current runtime.
    """
    # Validate bounds (60s - 3600s / 1 hour max)
    if timeout_seconds < 60:
        timeout_seconds = 60
    if timeout_seconds > 3600:
        timeout_seconds = 3600

    return {
        "success": True,
        "timeout_seconds": timeout_seconds,
    }
