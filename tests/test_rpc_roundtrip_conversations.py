"""RPC round-trip tests for the conversation lifecycle with a real DB.

Exercises the full JSON-RPC 2.0 dispatch path through _handle_jsonrpc_request
for conversation-related methods. No LLM calls. Archive handlers are tested
with mocked ArchiveService / StateBriefingService.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def rpc_db(tmp_path, monkeypatch, isolated_db_singleton):
    """Isolated DB for round-trip RPC tests.

    Resets both the cairn.db singleton (handled by isolated_db_singleton) and
    the play_db thread-local connection so ConversationService starts clean.
    Also resets the module-level _service singleton in rpc_handlers.conversations
    so each test gets a fresh ConversationService bound to the new play_db path.
    """
    monkeypatch.setenv("TALKINGROCK_DATA_DIR", str(tmp_path / "data"))

    import cairn.play_db as play_db
    import cairn.rpc_handlers.conversations as conv_handlers
    import cairn.rpc_handlers.briefing as briefing_handlers

    play_db.close_connection()
    play_db.init_db()

    # Reset service singletons so they pick up the new play_db connection.
    conv_handlers._service = None
    briefing_handlers._service = None

    from cairn.db import get_db

    db = get_db()
    yield db

    play_db.close_connection()
    conv_handlers._service = None
    briefing_handlers._service = None


# =============================================================================
# RPC helper
# =============================================================================


def _rpc(db, *, req_id: int, method: str, params: dict | None = None) -> dict:
    """Dispatch a JSON-RPC 2.0 request and return the full response envelope."""
    import cairn.ui_rpc_server as ui

    req: dict[str, Any] = {"jsonrpc": "2.0", "id": req_id, "method": method}
    p = dict(params) if params else {}
    p.setdefault("__session", "test-session")
    req["params"] = p
    resp = ui._handle_jsonrpc_request(db, req)
    assert resp is not None
    return resp


# =============================================================================
# Conversation listing (lifecycle handler)
# =============================================================================


def test_lifecycle_conversations_list_returns_empty_on_fresh_db(rpc_db) -> None:
    """lifecycle/conversations/list returns an empty list when no conversations exist."""
    resp = _rpc(rpc_db, req_id=1, method="lifecycle/conversations/list")

    assert "result" in resp
    assert resp["result"]["conversations"] == []


def test_lifecycle_conversations_list_returns_started_conversation(rpc_db) -> None:
    """lifecycle/conversations/list includes a conversation created via start."""
    # Start a conversation through the lifecycle service so the block FK is satisfied.
    _rpc(rpc_db, req_id=1, method="lifecycle/conversations/start")

    resp = _rpc(rpc_db, req_id=2, method="lifecycle/conversations/list")

    assert "result" in resp
    convs = resp["result"]["conversations"]
    assert len(convs) == 1
    assert convs[0]["status"] == "active"


def test_lifecycle_conversations_list_filtered_by_status(rpc_db) -> None:
    """lifecycle/conversations/list status filter excludes non-matching conversations."""
    _rpc(rpc_db, req_id=1, method="lifecycle/conversations/start")

    resp = _rpc(
        rpc_db,
        req_id=2,
        method="lifecycle/conversations/list",
        params={"status": "archived"},
    )

    assert "result" in resp
    # Active conversation should not appear when filtering for archived
    assert resp["result"]["conversations"] == []


# =============================================================================
# Get active conversation
# =============================================================================


def test_lifecycle_get_active_returns_none_on_fresh_db(rpc_db) -> None:
    """lifecycle/conversations/get_active returns None when no conversation is active."""
    resp = _rpc(rpc_db, req_id=1, method="lifecycle/conversations/get_active")

    assert "result" in resp
    assert resp["result"]["conversation"] is None


def test_lifecycle_get_active_returns_started_conversation(rpc_db) -> None:
    """lifecycle/conversations/get_active returns the conversation after start."""
    _rpc(rpc_db, req_id=1, method="lifecycle/conversations/start")

    resp = _rpc(rpc_db, req_id=2, method="lifecycle/conversations/get_active")

    assert "result" in resp
    conv = resp["result"]["conversation"]
    assert conv is not None
    assert conv["status"] == "active"


# =============================================================================
# Message operations (lifecycle handler)
# =============================================================================


def test_lifecycle_conversations_messages_empty_after_start(rpc_db) -> None:
    """lifecycle/conversations/messages returns empty list for a new conversation."""
    start_resp = _rpc(rpc_db, req_id=1, method="lifecycle/conversations/start")
    conv_id = start_resp["result"]["conversation"]["id"]

    resp = _rpc(
        rpc_db,
        req_id=2,
        method="lifecycle/conversations/messages",
        params={"conversation_id": conv_id},
    )

    assert "result" in resp
    assert resp["result"]["messages"] == []


def test_lifecycle_conversations_messages_after_add_message(rpc_db) -> None:
    """lifecycle/conversations/messages includes messages added via add_message."""
    start_resp = _rpc(rpc_db, req_id=1, method="lifecycle/conversations/start")
    conv_id = start_resp["result"]["conversation"]["id"]

    _rpc(
        rpc_db,
        req_id=2,
        method="lifecycle/conversations/add_message",
        params={"conversation_id": conv_id, "role": "user", "content": "Hello Cairn"},
    )

    resp = _rpc(
        rpc_db,
        req_id=3,
        method="lifecycle/conversations/messages",
        params={"conversation_id": conv_id},
    )

    assert "result" in resp
    messages = resp["result"]["messages"]
    assert len(messages) == 1
    assert messages[0]["content"] == "Hello Cairn"
    assert messages[0]["role"] == "user"


def test_lifecycle_conversations_messages_missing_param_returns_error(rpc_db) -> None:
    """lifecycle/conversations/messages with no conversation_id returns error -32602."""
    resp = _rpc(rpc_db, req_id=1, method="lifecycle/conversations/messages", params={})

    assert "error" in resp
    assert resp["error"]["code"] == -32602


# =============================================================================
# chat/clear (chat handler — uses db.py Database object)
# =============================================================================


def test_chat_clear_removes_conversation_and_messages(rpc_db) -> None:
    """chat/clear deletes a conversation and all its messages from the db.py database.

    chat/clear operates on the db.py (cairn.db.Database) connection, not play_db.
    Conversations are created via db.create_conversation and messages via db.add_message.
    Verification uses db.iter_conversations, which reads from the same db.py connection.
    """
    import uuid

    conv_id = uuid.uuid4().hex[:12]
    rpc_db.create_conversation(conversation_id=conv_id)
    rpc_db.add_message(
        message_id=uuid.uuid4().hex[:12],
        conversation_id=conv_id,
        role="user",
        content="Test message",
    )

    # Verify the conversation exists before clear.
    before = rpc_db.iter_conversations()
    assert any(c["id"] == conv_id for c in before)

    # Clear via chat/clear (uses db.py connection).
    clear_resp = _rpc(
        rpc_db,
        req_id=1,
        method="chat/clear",
        params={"conversation_id": conv_id},
    )
    assert "result" in clear_resp
    assert clear_resp["result"]["ok"] is True

    # Conversation should no longer appear via db.iter_conversations.
    after = rpc_db.iter_conversations()
    assert all(c["id"] != conv_id for c in after)


def test_chat_clear_missing_conversation_id_returns_error(rpc_db) -> None:
    """chat/clear with missing conversation_id returns error -32602."""
    resp = _rpc(rpc_db, req_id=1, method="chat/clear", params={})

    assert "error" in resp
    assert resp["error"]["code"] == -32602


# =============================================================================
# Archive list
# =============================================================================


def test_archive_list_empty_on_fresh_db(rpc_db) -> None:
    """archive/list returns empty archives list on a fresh DB."""
    resp = _rpc(rpc_db, req_id=1, method="archive/list")

    assert "result" in resp
    assert resp["result"]["archives"] == []


# =============================================================================
# archive/get — not-found error
# =============================================================================


def test_archive_get_not_found_returns_error(rpc_db) -> None:
    """archive/get returns an RPC error when the archive_id does not exist."""
    resp = _rpc(
        rpc_db,
        req_id=1,
        method="archive/get",
        params={"archive_id": "nonexistent-archive-id"},
    )

    assert "error" in resp
    assert resp["error"]["code"] == -32602


# =============================================================================
# conversation/archive/preview — mock ArchiveService
# =============================================================================


def test_conversation_archive_preview_dispatches_to_archive_service(rpc_db) -> None:
    """conversation/archive/preview calls ArchiveService.preview_archive."""
    start_resp = _rpc(rpc_db, req_id=1, method="lifecycle/conversations/start")
    conv_id = start_resp["result"]["conversation"]["id"]

    mock_preview = MagicMock()
    mock_preview.to_dict.return_value = {
        "conversation_id": conv_id,
        "title": "Preview Title",
        "summary": "Preview summary.",
        "knowledge_entries": [],
    }

    with patch("cairn.services.archive_service.ArchiveService.preview_archive", return_value=mock_preview):
        resp = _rpc(
            rpc_db,
            req_id=2,
            method="conversation/archive/preview",
            params={"conversation_id": conv_id},
        )

    assert "result" in resp
    result = resp["result"]
    assert result["title"] == "Preview Title"


# =============================================================================
# conversation/archive — mock ArchiveService
# =============================================================================


def test_conversation_archive_dispatches_to_archive_service(rpc_db) -> None:
    """conversation/archive calls ArchiveService.archive_conversation."""
    start_resp = _rpc(rpc_db, req_id=1, method="lifecycle/conversations/start")
    conv_id = start_resp["result"]["conversation"]["id"]

    mock_result = MagicMock()
    mock_result.to_dict.return_value = {
        "conversation_id": conv_id,
        "archived": True,
        "knowledge_count": 0,
    }

    with patch(
        "cairn.services.archive_service.ArchiveService.archive_conversation",
        return_value=mock_result,
    ):
        resp = _rpc(
            rpc_db,
            req_id=2,
            method="conversation/archive",
            params={"conversation_id": conv_id},
        )

    assert "result" in resp
    assert resp["result"]["archived"] is True


# =============================================================================
# conversation/archive/confirm — mock ArchiveService
# =============================================================================


def test_conversation_archive_confirm_dispatches_to_archive_service(rpc_db) -> None:
    """conversation/archive/confirm calls ArchiveService.archive_with_review."""
    start_resp = _rpc(rpc_db, req_id=1, method="lifecycle/conversations/start")
    conv_id = start_resp["result"]["conversation"]["id"]

    mock_result = MagicMock()
    mock_result.to_dict.return_value = {
        "conversation_id": conv_id,
        "archived": True,
        "title": "Confirmed Title",
    }

    with patch(
        "cairn.services.archive_service.ArchiveService.archive_with_review",
        return_value=mock_result,
    ):
        resp = _rpc(
            rpc_db,
            req_id=2,
            method="conversation/archive/confirm",
            params={
                "conversation_id": conv_id,
                "title": "Confirmed Title",
                "summary": "A confirmed archive.",
                "knowledge_entries": [],
            },
        )

    assert "result" in resp
    assert resp["result"]["archived"] is True


# =============================================================================
# conversation/delete — mock ArchiveService
# =============================================================================


def test_conversation_delete_dispatches_to_archive_service(rpc_db) -> None:
    """conversation/delete calls ArchiveService.delete_conversation."""
    start_resp = _rpc(rpc_db, req_id=1, method="lifecycle/conversations/start")
    conv_id = start_resp["result"]["conversation"]["id"]

    with patch(
        "cairn.services.archive_service.ArchiveService.delete_conversation",
        return_value={"deleted": True, "conversation_id": conv_id},
    ):
        resp = _rpc(
            rpc_db,
            req_id=2,
            method="conversation/delete",
            params={"conversation_id": conv_id},
        )

    assert "result" in resp
    assert resp["result"]["deleted"] is True


# =============================================================================
# archive/feedback — mock ArchiveService
# =============================================================================


def test_archive_feedback_dispatches_to_archive_service(rpc_db) -> None:
    """archive/feedback calls ArchiveService.submit_user_feedback."""
    with patch(
        "cairn.services.archive_service.ArchiveService.submit_user_feedback",
        return_value={"submitted": True, "archive_id": "fake-archive"},
    ):
        resp = _rpc(
            rpc_db,
            req_id=1,
            method="archive/feedback",
            params={"archive_id": "fake-archive", "rating": 4, "feedback": "Good job"},
        )

    assert "result" in resp
    assert resp["result"]["submitted"] is True


def test_archive_feedback_rejects_out_of_range_rating(rpc_db) -> None:
    """archive/feedback returns error -32602 for rating outside 1-5."""
    resp = _rpc(
        rpc_db,
        req_id=1,
        method="archive/feedback",
        params={"archive_id": "fake-archive", "rating": 10},
    )

    assert "error" in resp
    assert resp["error"]["code"] == -32602


# =============================================================================
# lifecycle/briefing/get
# =============================================================================


def test_briefing_get_returns_none_on_fresh_db(rpc_db) -> None:
    """lifecycle/briefing/get returns None briefing when none has been generated."""
    resp = _rpc(rpc_db, req_id=1, method="lifecycle/briefing/get")

    assert "result" in resp
    assert resp["result"]["briefing"] is None


# =============================================================================
# lifecycle/briefing/generate — mock StateBriefingService
# =============================================================================


def test_briefing_generate_dispatches_to_briefing_service(rpc_db) -> None:
    """lifecycle/briefing/generate calls StateBriefingService.generate."""
    mock_briefing = MagicMock()
    mock_briefing.to_dict.return_value = {
        "id": "briefing-test-01",
        "content": "You have 2 open tasks.",
        "trigger": "manual",
    }

    with patch(
        "cairn.services.state_briefing_service.StateBriefingService.generate",
        return_value=mock_briefing,
    ):
        resp = _rpc(
            rpc_db,
            req_id=1,
            method="lifecycle/briefing/generate",
            params={"trigger": "manual"},
        )

    assert "result" in resp
    assert resp["result"]["briefing"]["content"] == "You have 2 open tasks."


# =============================================================================
# Full lifecycle integration: start → add message → list → clear
# =============================================================================


def test_full_lifecycle_create_add_messages_and_list(rpc_db) -> None:
    """Start a conversation, add messages, verify listing and message retrieval.

    This tests the full lifecycle path using play_db-backed lifecycle handlers.
    """
    # Start
    start_resp = _rpc(rpc_db, req_id=1, method="lifecycle/conversations/start")
    assert "result" in start_resp
    conv_id = start_resp["result"]["conversation"]["id"]

    # Add two messages
    _rpc(
        rpc_db,
        req_id=2,
        method="lifecycle/conversations/add_message",
        params={"conversation_id": conv_id, "role": "user", "content": "First message"},
    )
    _rpc(
        rpc_db,
        req_id=3,
        method="lifecycle/conversations/add_message",
        params={"conversation_id": conv_id, "role": "cairn", "content": "Reply"},
    )

    # List: one non-system conversation with status active
    list_resp = _rpc(rpc_db, req_id=4, method="lifecycle/conversations/list")
    active_convs = [c for c in list_resp["result"]["conversations"] if c["status"] == "active"]
    assert len(active_convs) == 1
    assert active_convs[0]["id"] == conv_id

    # Messages: two
    msg_resp = _rpc(
        rpc_db,
        req_id=5,
        method="lifecycle/conversations/messages",
        params={"conversation_id": conv_id},
    )
    assert len(msg_resp["result"]["messages"]) == 2

    # get_active returns the same conversation
    active_resp = _rpc(rpc_db, req_id=6, method="lifecycle/conversations/get_active")
    assert active_resp["result"]["conversation"]["id"] == conv_id


def test_chat_clear_removes_db_conversation(rpc_db) -> None:
    """chat/clear removes a db.py-layer conversation from db.iter_conversations.

    chat/clear operates on db.py (the cairn.db.Database connection), not play_db.
    A fresh db.py conversation is created via db.create_conversation and verified
    via db.iter_conversations so both operations share the same database layer.
    """
    import uuid

    conv_id = uuid.uuid4().hex[:12]
    rpc_db.create_conversation(conversation_id=conv_id)
    rpc_db.add_message(
        message_id=uuid.uuid4().hex[:12],
        conversation_id=conv_id,
        role="user",
        content="Message for db-layer conversation",
    )

    # Verify existence
    before = rpc_db.iter_conversations()
    assert any(c["id"] == conv_id for c in before)

    # Clear via RPC
    clear_resp = _rpc(
        rpc_db,
        req_id=1,
        method="chat/clear",
        params={"conversation_id": conv_id},
    )
    assert clear_resp["result"]["ok"] is True

    # Verify gone
    after = rpc_db.iter_conversations()
    assert all(c["id"] != conv_id for c in after)
