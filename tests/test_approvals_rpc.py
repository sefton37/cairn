"""Unit tests for the approvals/ RPC handler functions.

Tests verify:
- handle_approval_pending returns pending approvals from DB
- handle_approval_respond validates approval existence, handles approve/reject
- handle_approval_explain returns explanation for a stored approval
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest


def _mock_db() -> MagicMock:
    db = MagicMock()
    db.get_pending_approvals.return_value = []
    db.get_approval.return_value = None
    return db


def _make_approval(
    approval_id: str = "appr-1",
    status: str = "pending",
    command: str | None = None,
    explanation: str = "Run a command",
) -> dict:
    return {
        "id": approval_id,
        "conversation_id": "conv-1",
        "command": command or json.dumps({"user_request": "do thing", "agent_type": "cairn"}),
        "explanation": explanation,
        "risk_level": "low",
        "affected_paths": "[]",
        "undo_command": None,
        "plan_id": None,
        "step_id": None,
        "created_at": "2026-01-01T00:00:00Z",
        "status": status,
    }


# =============================================================================
# handle_approval_pending
# =============================================================================


class TestHandleApprovalPending:
    """handle_approval_pending returns the list of pending approvals."""

    def test_returns_empty_list_when_no_pending_approvals(self) -> None:
        from cairn.rpc_handlers.approvals import handle_approval_pending

        db = _mock_db()
        result = handle_approval_pending(db)

        assert result == {"approvals": []}

    def test_returns_approvals_with_expected_fields(self) -> None:
        from cairn.rpc_handlers.approvals import handle_approval_pending

        db = _mock_db()
        db.get_pending_approvals.return_value = [_make_approval()]

        result = handle_approval_pending(db)

        assert len(result["approvals"]) == 1
        appr = result["approvals"][0]
        assert appr["id"] == "appr-1"
        assert appr["risk_level"] == "low"
        assert appr["affected_paths"] == []

    def test_passes_conversation_id_filter_to_db(self) -> None:
        from cairn.rpc_handlers.approvals import handle_approval_pending

        db = _mock_db()
        handle_approval_pending(db, conversation_id="conv-abc")

        db.get_pending_approvals.assert_called_once_with(conversation_id="conv-abc")


# =============================================================================
# handle_approval_respond
# =============================================================================


class TestHandleApprovalRespond:
    """handle_approval_respond handles approve and reject actions."""

    def test_raises_rpc_error_when_approval_not_found(self) -> None:
        from cairn.rpc_handlers import RpcError
        from cairn.rpc_handlers.approvals import handle_approval_respond

        db = _mock_db()
        db.get_approval.return_value = None

        with pytest.raises(RpcError) as exc_info:
            handle_approval_respond(db, approval_id="ghost", action="approve")

        assert exc_info.value.code == -32602
        assert "not found" in exc_info.value.message

    def test_raises_rpc_error_when_approval_already_resolved(self) -> None:
        from cairn.rpc_handlers import RpcError
        from cairn.rpc_handlers.approvals import handle_approval_respond

        db = _mock_db()
        db.get_approval.return_value = _make_approval(status="approved")

        with pytest.raises(RpcError) as exc_info:
            handle_approval_respond(db, approval_id="appr-1", action="approve")

        assert exc_info.value.code == -32602
        assert "already resolved" in exc_info.value.message

    def test_returns_rejected_status_for_reject_action(self) -> None:
        from cairn.rpc_handlers.approvals import handle_approval_respond

        db = _mock_db()
        db.get_approval.return_value = _make_approval()

        with (
            patch("cairn.rpc_handlers.approvals.check_rate_limit"),
            patch("cairn.rpc_handlers.approvals.audit_log"),
        ):
            result = handle_approval_respond(db, approval_id="appr-1", action="reject")

        assert result["status"] == "rejected"
        assert result["result"] is None
        db.resolve_approval.assert_called_once_with(approval_id="appr-1", status="rejected")

    def test_raises_rpc_error_for_invalid_action(self) -> None:
        from cairn.rpc_handlers import RpcError
        from cairn.rpc_handlers.approvals import handle_approval_respond

        db = _mock_db()
        db.get_approval.return_value = _make_approval()

        with (
            patch("cairn.rpc_handlers.approvals.check_rate_limit"),
            patch("cairn.rpc_handlers.approvals.audit_log"),
        ):
            with pytest.raises(RpcError) as exc_info:
                handle_approval_respond(db, approval_id="appr-1", action="maybe")

        assert exc_info.value.code == -32602
        assert "Invalid action" in exc_info.value.message

    def test_approve_action_calls_chat_agent_and_returns_executed_status(self) -> None:
        from cairn.rpc_handlers.approvals import handle_approval_respond

        db = _mock_db()
        db.get_approval.return_value = _make_approval()

        fake_response = MagicMock()
        fake_response.answer = "Done."
        fake_response.tool_calls = []
        fake_response.message_id = "msg-123"

        fake_agent = MagicMock()
        fake_agent.respond.return_value = fake_response

        with (
            patch("cairn.rpc_handlers.approvals.check_rate_limit"),
            patch("cairn.rpc_handlers.approvals.audit_log"),
            patch("cairn.agent.ChatAgent", return_value=fake_agent),
        ):
            result = handle_approval_respond(db, approval_id="appr-1", action="approve")

        assert result["status"] == "executed"
        assert result["result"]["answer"] == "Done."


# =============================================================================
# handle_approval_explain
# =============================================================================


class TestHandleApprovalExplain:
    """handle_approval_explain returns explanation for an approval."""

    def test_raises_rpc_error_when_approval_not_found(self) -> None:
        from cairn.rpc_handlers import RpcError
        from cairn.rpc_handlers.approvals import handle_approval_explain

        db = _mock_db()
        db.get_approval.return_value = None

        with pytest.raises(RpcError) as exc_info:
            handle_approval_explain(db, approval_id="ghost")

        assert exc_info.value.code == -32602

    def test_returns_explanation_and_command(self) -> None:
        from cairn.rpc_handlers.approvals import handle_approval_explain

        db = _mock_db()
        db.get_approval.return_value = _make_approval(explanation="A detailed explanation.")

        result = handle_approval_explain(db, approval_id="appr-1")

        assert "A detailed explanation." in result["explanation"]
        assert result["affected_paths"] == []
        assert result["warnings"] == []

    def test_falls_back_to_default_explanation_when_none(self) -> None:
        from cairn.rpc_handlers.approvals import handle_approval_explain

        db = _mock_db()
        appr = _make_approval()
        appr["explanation"] = None
        db.get_approval.return_value = appr

        result = handle_approval_explain(db, approval_id="appr-1")

        assert "No explanation available" in result["explanation"]
