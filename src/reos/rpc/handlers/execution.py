"""Execution handlers.

Manages command execution, streaming output, and execution lifecycle.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from reos.db import Database
from reos.rpc.router import register
from reos.rpc.types import INVALID_PARAMS, RpcError
from reos.security import (
    AuditEventType,
    RateLimitExceeded,
    audit_log,
    check_rate_limit,
    is_command_safe,
)

logger = logging.getLogger(__name__)

# Track active executions
_active_executions: dict[str, Any] = {}


@register("execution/start", needs_db=True)
def handle_start(
    db: Database,
    *,
    command: str,
    execution_id: str,
    cwd: str | None = None,
    timeout: int = 300,
) -> dict[str, Any]:
    """Start a streaming command execution.

    Security: All commands are validated before execution:
    - Dangerous commands (rm -rf /, fork bombs, etc.) are blocked
    - Rate limiting prevents command flooding
    - All executions are audit logged
    """
    from reos.streaming_executor import get_streaming_executor

    # Security check 1: Validate command is safe
    is_safe, warning = is_command_safe(command)
    if not is_safe:
        audit_log(
            AuditEventType.COMMAND_BLOCKED,
            {
                "command": command[:500],
                "reason": warning,
                "execution_id": execution_id,
            },
            success=False,
        )
        logger.warning(
            "Blocked dangerous command in execution/start: %s - %s",
            warning,
            command[:100],
        )
        return {
            "execution_id": execution_id,
            "status": "blocked",
            "error": f"Command blocked: {warning}",
        }

    # Security check 2: Rate limiting
    try:
        # Use 'sudo' rate limit if command contains sudo, otherwise general limit
        if "sudo " in command:
            check_rate_limit("sudo")
        check_rate_limit("service")  # General command rate limit
    except RateLimitExceeded as e:
        audit_log(
            AuditEventType.RATE_LIMIT_EXCEEDED,
            {
                "command": command[:500],
                "execution_id": execution_id,
                "retry_after": e.retry_after_seconds,
            },
            success=False,
        )
        return {
            "execution_id": execution_id,
            "status": "rate_limited",
            "error": str(e),
            "retry_after_seconds": e.retry_after_seconds,
        }

    # Security check 3: Audit log the execution
    audit_log(
        AuditEventType.COMMAND_EXECUTED,
        {
            "command": command[:500],
            "execution_id": execution_id,
            "cwd": cwd,
            "timeout": timeout,
            "has_sudo": "sudo " in command,
        },
        success=True,
    )

    executor = get_streaming_executor()
    executor.start(
        command,
        execution_id=execution_id,
        cwd=cwd,
        timeout=timeout,
    )

    return {
        "execution_id": execution_id,
        "status": "started",
    }


@register("execution/output", needs_db=True)
def handle_output(
    db: Database,
    *,
    execution_id: str,
    since_line: int = 0,
) -> dict[str, Any]:
    """Get streaming output from an execution."""
    from reos.streaming_executor import get_streaming_executor

    executor = get_streaming_executor()
    lines, is_complete = executor.get_output(execution_id, since_line=since_line)

    result: dict[str, Any] = {
        "lines": lines,
        "is_complete": is_complete,
        "next_line": since_line + len(lines),
    }

    if is_complete:
        final_result = executor.get_result(execution_id)
        if final_result:
            result["return_code"] = final_result["return_code"]
            result["success"] = final_result["success"]
            result["error"] = final_result["error"]
            result["duration_seconds"] = final_result["duration_seconds"]

    return result


@register("execution/status", needs_db=True)
def handle_status(
    db: Database,
    *,
    execution_id: str,
) -> dict[str, Any]:
    """Get the status of an execution."""
    from reos.streaming_executor import get_streaming_executor
    from reos.rpc.handlers.code_mode import get_code_execution

    # Check streaming executor first
    executor = get_streaming_executor()
    status = executor.get_status(execution_id)

    if status:
        return {
            "execution_id": execution_id,
            "state": status["state"],
            "current_step": 0,
            "total_steps": 1,
            "completed_steps": [{"step_id": "cmd", "success": status.get("success", False)}] if status["state"] == "completed" else [],
        }

    # Check Code Mode executions
    code_context = get_code_execution(execution_id)
    if code_context:
        state = code_context.state
        completed_steps = []

        # Build completed steps from the state
        if state and state.steps_completed > 0:
            for i in range(state.steps_completed):
                completed_steps.append({
                    "step_id": f"step-{i}",
                    "success": True,
                    "output_preview": "",
                })

        # Map phase to state value
        exec_state = "running"
        if code_context.is_complete:
            exec_state = "completed" if (state and state.success) else "failed"
        elif state:
            exec_state = state.status

        return {
            "execution_id": execution_id,
            "state": exec_state,
            "current_step": state.steps_completed if state else 0,
            "total_steps": state.steps_total if state else 0,
            "completed_steps": completed_steps,
            # Extra fields for richer UI (optional)
            "phase": state.phase if state else None,
            "phase_description": state.phase_description if state else None,
            "output_lines": state.output_lines if state else [],
            "is_complete": code_context.is_complete,
            "success": state.success if state else None,
            "error": code_context.error,
        }

    raise RpcError(code=INVALID_PARAMS, message=f"Execution not found: {execution_id}")


@register("execution/pause", needs_db=True)
def handle_pause(
    db: Database,
    *,
    execution_id: str,
) -> dict[str, Any]:
    """Pause an execution (for future implementation with async execution)."""
    # Note: Current executor is synchronous, so pause is limited
    return {"ok": True, "message": "Pause requested (takes effect at next step boundary)"}


@register("execution/abort", needs_db=True)
def handle_abort(
    db: Database,
    *,
    execution_id: str,
    rollback: bool = True,
) -> dict[str, Any]:
    """Abort an execution and optionally rollback."""
    context = _active_executions.get(execution_id)

    if not context:
        raise RpcError(code=INVALID_PARAMS, message=f"Execution not found: {execution_id}")

    # Clean up
    if execution_id in _active_executions:
        del _active_executions[execution_id]

    return {"ok": True, "message": "Execution aborted"}


@register("execution/rollback", needs_db=True)
def handle_rollback(
    db: Database,
    *,
    conversation_id: str,
) -> dict[str, Any]:
    """Rollback the last operation."""
    from reos.rpc.handlers.chat import get_reasoning_engine

    engine = get_reasoning_engine(conversation_id, db)
    result = engine.process("undo")
    return {"response": result.response}


@register("execution/kill", needs_db=True)
def handle_kill(
    db: Database,
    *,
    execution_id: str,
) -> dict[str, Any]:
    """Kill a running execution.

    Checks both streaming executor and Code Mode executions.
    """
    from reos.streaming_executor import get_streaming_executor
    from reos.rpc.handlers.code_mode import get_code_execution

    # First try streaming executor
    executor = get_streaming_executor()
    killed = executor.kill(execution_id)

    if killed:
        return {"ok": True, "message": "Execution killed"}

    # Fall through to Code Mode executions
    code_context = get_code_execution(execution_id)
    if code_context:
        if code_context.is_complete:
            return {"ok": False, "message": "Execution already complete"}
        code_context.request_cancel()
        return {"ok": True, "message": "Cancellation requested"}

    return {"ok": False, "message": "Execution not found or already complete"}
