"""Handoff handlers.

Manages multi-agent handoff system for CAIRN, RIVA, and ReOS agents.
"""

from __future__ import annotations

import threading
from typing import Any

from reos.db import Database
from reos.rpc.router import register


# Global state for handoff management (per-session)
# Protected by _handoff_lock for thread safety
_handoff_state: dict[str, Any] = {
    "current_agent": "cairn",  # Default entry point
    "pending_handoff": None,
    "handler": None,
}
_handoff_lock = threading.Lock()


def _get_handoff_handler():
    """Get or create the handoff handler.

    Note: Caller must hold _handoff_lock.
    """
    from reos.handoff import AgentType, SharedToolHandler

    if _handoff_state["handler"] is None:
        current = AgentType(_handoff_state["current_agent"])
        _handoff_state["handler"] = SharedToolHandler(current_agent=current)
    return _handoff_state["handler"]


@register("handoff/status", needs_db=True)
def handle_status(_db: Database) -> dict[str, Any]:
    """Get current handoff/agent status."""
    from reos.handoff import get_agent_manifest, AgentType, AGENT_DESCRIPTIONS

    with _handoff_lock:
        current = _handoff_state["current_agent"]
        pending_handoff = _handoff_state["pending_handoff"]

    manifest = get_agent_manifest(AgentType(current))
    agent_info = AGENT_DESCRIPTIONS[AgentType(current)]

    pending = None
    if pending_handoff:
        pending = pending_handoff.to_dict()

    return {
        "current_agent": current,
        "agent_name": agent_info["name"],
        "agent_role": agent_info["role"],
        "agent_domain": agent_info["domain"],
        "tool_count": manifest["tool_count"],
        "pending_handoff": pending,
        "available_agents": ["cairn", "reos", "riva"],
    }


@register("handoff/propose", needs_db=True)
def handle_propose(
    _db: Database,
    *,
    target_agent: str,
    user_goal: str,
    handoff_reason: str,
    relevant_details: list[str] | None = None,
    relevant_paths: list[str] | None = None,
    open_ui: bool = True,
) -> dict[str, Any]:
    """Propose a handoff to another agent (requires user confirmation)."""
    with _handoff_lock:
        handler = _get_handoff_handler()

        result = handler.call_tool("handoff_to_agent", {
            "target_agent": target_agent,
            "user_goal": user_goal,
            "handoff_reason": handoff_reason,
            "relevant_details": relevant_details or [],
            "relevant_paths": relevant_paths or [],
            "open_ui": open_ui,
        })

        # Store pending handoff in global state
        if handler.pending_handoff:
            _handoff_state["pending_handoff"] = handler.pending_handoff

    return result


@register("handoff/confirm", needs_db=True)
def handle_confirm(_db: Database, *, handoff_id: str) -> dict[str, Any]:
    """Confirm a pending handoff."""
    from reos.handoff import AgentType, SharedToolHandler

    with _handoff_lock:
        handler = _get_handoff_handler()
        result = handler.confirm_handoff(handoff_id)

        if result.get("status") == "confirmed":
            # Update current agent
            new_agent = result["target_agent"]
            _handoff_state["current_agent"] = new_agent
            _handoff_state["pending_handoff"] = None

            # Create new handler for new agent
            _handoff_state["handler"] = SharedToolHandler(
                current_agent=AgentType(new_agent)
            )

            result["message"] = f"Switched to {new_agent}. How can I help?"

    return result


@register("handoff/reject", needs_db=True)
def handle_reject(
    _db: Database,
    *,
    handoff_id: str,
    reason: str | None = None,
) -> dict[str, Any]:
    """Reject a pending handoff."""
    with _handoff_lock:
        handler = _get_handoff_handler()
        result = handler.reject_handoff(
            handoff_id,
            reason=reason or "User chose to stay with current agent",
        )

        _handoff_state["pending_handoff"] = None

    return result


@register("handoff/detect", needs_db=True)
def handle_detect(
    _db: Database,
    *,
    message: str,
) -> dict[str, Any]:
    """Detect if a message should trigger a handoff suggestion."""
    from reos.handoff import detect_handoff_need, AgentType

    with _handoff_lock:
        current_agent = _handoff_state["current_agent"]

    current = AgentType(current_agent)
    decision = detect_handoff_need(current, message)

    return decision.to_dict()


@register("handoff/switch", needs_db=True)
def handle_switch(
    _db: Database,
    *,
    target_agent: str,
) -> dict[str, Any]:
    """Directly switch to another agent (user-initiated, no confirmation)."""
    from reos.handoff import AgentType, SharedToolHandler, AGENT_DESCRIPTIONS

    if target_agent not in ["cairn", "reos", "riva"]:
        return {"status": "error", "reason": f"Unknown agent: {target_agent}"}

    with _handoff_lock:
        old_agent = _handoff_state["current_agent"]
        _handoff_state["current_agent"] = target_agent
        _handoff_state["pending_handoff"] = None
        _handoff_state["handler"] = SharedToolHandler(
            current_agent=AgentType(target_agent)
        )

    agent_info = AGENT_DESCRIPTIONS[AgentType(target_agent)]

    return {
        "status": "switched",
        "from_agent": old_agent,
        "to_agent": target_agent,
        "agent_name": agent_info["name"],
        "agent_role": agent_info["role"],
        "message": f"Switched to {agent_info['name']}. {agent_info['personality'].capitalize()}.",
    }


@register("handoff/manifest", needs_db=True)
def handle_manifest(
    _db: Database,
    *,
    agent: str | None = None,
) -> dict[str, Any]:
    """Get tool manifest for an agent."""
    from reos.handoff import get_agent_manifest, AgentType

    if agent:
        target = agent
    else:
        with _handoff_lock:
            target = _handoff_state["current_agent"]

    manifest = get_agent_manifest(AgentType(target))

    return manifest


@register("handoff/validate", needs_db=True)
def handle_validate(_db: Database) -> dict[str, Any]:
    """Validate all agent manifests (15-tool cap check)."""
    from reos.handoff import validate_all_manifests

    return validate_all_manifests()
