"""Approval workflow RPC handlers.

These handlers manage the approval workflow for potentially
dangerous commands that require user confirmation before execution.
"""

from __future__ import annotations

import json
from typing import Any

from cairn.db import Database
from cairn.security import (
    check_rate_limit,
    RateLimitExceeded,
    audit_log,
    AuditEventType,
)

from . import RpcError


# =============================================================================
# Approval Handlers
# =============================================================================


def handle_approval_pending(
    db: Database,
    *,
    conversation_id: str | None = None,
) -> dict[str, Any]:
    """Get all pending approvals."""
    approvals = db.get_pending_approvals(conversation_id=conversation_id)
    return {
        "approvals": [
            {
                "id": str(a.get("id")),
                "conversation_id": a.get("conversation_id"),
                "command": a.get("command"),
                "explanation": a.get("explanation"),
                "risk_level": a.get("risk_level"),
                "affected_paths": json.loads(a.get("affected_paths") or "[]"),
                "undo_command": a.get("undo_command"),
                "plan_id": a.get("plan_id"),
                "step_id": a.get("step_id"),
                "created_at": a.get("created_at"),
            }
            for a in approvals
        ]
    }


def handle_approval_respond(
    db: Database,
    *,
    approval_id: str,
    action: str,  # 'approve', 'reject'
    edited_command: str | None = None,
) -> dict[str, Any]:
    """Respond to an approval request."""
    approval = db.get_approval(approval_id=approval_id)
    if approval is None:
        raise RpcError(code=-32602, message=f"Approval not found: {approval_id}")

    if approval.get("status") != "pending":
        raise RpcError(code=-32602, message="Approval already resolved")

    # SECURITY: Rate limit approval actions
    try:
        check_rate_limit("approval")
    except RateLimitExceeded as e:
        audit_log(AuditEventType.RATE_LIMIT_EXCEEDED, {"category": "approval", "action": action})
        raise RpcError(code=-32429, message=str(e))

    if action == "reject":
        db.resolve_approval(approval_id=approval_id, status="rejected")
        audit_log(AuditEventType.APPROVAL_DENIED, {
            "approval_id": approval_id,
            "original_command": approval.get("command"),
        })
        return {"status": "rejected", "result": None}

    if action == "approve":
        db.resolve_approval(approval_id=approval_id, status="approved")

        # Re-execute the original request with force_approve to bypass the gate
        payload = json.loads(str(approval.get("command") or "{}"))
        user_request = payload.get("user_request", "")
        conversation_id = str(approval.get("conversation_id"))
        agent_type = payload.get("agent_type", "cairn")

        from cairn.agent import ChatAgent

        agent = ChatAgent(db=db)
        response = agent.respond(
            user_request,
            conversation_id=conversation_id,
            agent_type=agent_type,
            force_approve=True,
        )

        audit_log(AuditEventType.APPROVAL_GRANTED, {
            "approval_id": approval_id,
            "user_request": user_request[:200],
        })

        return {
            "status": "executed",
            "result": {
                "answer": response.answer,
                "tool_calls": response.tool_calls,
                "message_id": response.message_id,
            },
        }

    raise RpcError(code=-32602, message=f"Invalid action: {action}")


def handle_approval_explain(
    db: Database,
    *,
    approval_id: str,
) -> dict[str, Any]:
    """Get stored explanation for an approval request.

    Note: command preview (affected paths, undo info) is no longer available
    since linux_tools has been removed. Returns only the stored explanation.
    """
    approval = db.get_approval(approval_id=approval_id)
    if approval is None:
        raise RpcError(code=-32602, message=f"Approval not found: {approval_id}")

    command = str(approval.get("command"))
    explanation = approval.get("explanation") or "No explanation available."

    return {
        "command": command,
        "explanation": explanation,
        "detailed_explanation": f"Command: {command}\n\nDescription: {explanation}",
        "is_destructive": None,
        "can_undo": None,
        "undo_command": approval.get("undo_command"),
        "affected_paths": json.loads(approval.get("affected_paths") or "[]"),
        "warnings": [],
    }
