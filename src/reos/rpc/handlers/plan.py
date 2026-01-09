"""Plan handlers.

Manages plan preview, approval, and cancellation for the reasoning engine.
Note: These are distinct from code/plan/* handlers which handle Code Mode planning.
"""

from __future__ import annotations

import threading
from typing import Any

from reos.db import Database
from reos.rpc.router import register
from reos.rpc.types import RpcError


# Store reasoning engines per conversation
_reasoning_engines: dict[str, Any] = {}

# Store active executions from plan approvals
_active_executions: dict[str, Any] = {}


def _get_reasoning_engine(conversation_id: str, db: Database) -> Any:
    """Get or create a reasoning engine for a conversation."""
    from reos.reasoning.engine import ReasoningEngine

    if conversation_id not in _reasoning_engines:
        _reasoning_engines[conversation_id] = ReasoningEngine(db=db)
    return _reasoning_engines[conversation_id]


def get_reasoning_engine(conversation_id: str, db: Database) -> Any:
    """Public access to get reasoning engine for a conversation."""
    return _get_reasoning_engine(conversation_id, db)


def get_active_execution(execution_id: str) -> Any | None:
    """Get an active execution context by ID."""
    return _active_executions.get(execution_id)


@register("plan/preview", needs_db=True)
def handle_preview(
    db: Database,
    *,
    request: str,
    conversation_id: str,
) -> dict[str, Any]:
    """Preview a plan for a request without executing it."""
    engine = _get_reasoning_engine(conversation_id, db)
    result = engine.process(request)

    if not result.plan:
        return {
            "has_plan": False,
            "response": result.response,
            "complexity": result.complexity.level.value if result.complexity else None,
        }

    # Format plan steps
    steps = []
    for i, step in enumerate(result.plan.steps):
        risk_info = {}
        if step.risk:
            risk_info = {
                "level": step.risk.level.value if hasattr(step.risk.level, 'value') else str(step.risk.level),
                "requires_confirmation": step.risk.requires_confirmation,
                "reversible": step.risk.reversible,
            }

        steps.append({
            "number": i + 1,
            "id": step.id,
            "title": step.title,
            "command": step.command,
            "explanation": step.explanation,
            "risk": risk_info,
        })

    return {
        "has_plan": True,
        "plan_id": result.plan.id,
        "title": result.plan.title,
        "steps": steps,
        "needs_approval": result.needs_approval,
        "response": result.response,
        "complexity": result.complexity.level.value if result.complexity else None,
    }


@register("plan/approve", needs_db=True)
def handle_approve(
    db: Database,
    *,
    conversation_id: str,
) -> dict[str, Any]:
    """Approve and execute the pending plan."""
    engine = _get_reasoning_engine(conversation_id, db)

    if not engine.get_pending_plan():
        raise RpcError(code=-32602, message="No pending plan to approve")

    # Approve by sending "yes"
    result = engine.process("yes")

    # Track the execution context
    if result.execution_context:
        execution_id = result.plan.id if result.plan else conversation_id
        _active_executions[execution_id] = result.execution_context

    return {
        "status": "executed" if result.execution_context else "no_execution",
        "response": result.response,
        "execution_id": result.plan.id if result.plan else None,
    }


@register("plan/cancel", needs_db=True)
def handle_cancel(
    db: Database,
    *,
    conversation_id: str,
) -> dict[str, Any]:
    """Cancel the pending plan."""
    engine = _get_reasoning_engine(conversation_id, db)
    engine.cancel_pending()
    return {"ok": True, "message": "Plan cancelled"}
