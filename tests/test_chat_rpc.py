"""Unit tests for the chat/ RPC handler functions.

Tests verify:
- handle_chat_respond delegates to ChatAgent.respond and returns structured response
- handle_conversations_list wraps db.iter_conversations
- handle_conversation_messages wraps db.get_messages
- handle_chat_clear calls db.clear_messages and deletes the conversation row
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def _mock_db() -> MagicMock:
    db = MagicMock()
    db.iter_conversations.return_value = []
    db.get_messages.return_value = []
    db.transaction.return_value.__enter__ = MagicMock(return_value=MagicMock())
    db.transaction.return_value.__exit__ = MagicMock(return_value=False)
    return db


def _make_agent_response(
    answer: str = "Hello!",
    conversation_id: str = "conv-1",
    message_id: str = "msg-1",
) -> MagicMock:
    resp = MagicMock()
    resp.answer = answer
    resp.conversation_id = conversation_id
    resp.message_id = message_id
    resp.message_type = "text"
    resp.tool_calls = []
    resp.thinking_steps = []
    resp.pending_approval_id = None
    resp.extended_thinking_trace = None
    resp.user_message_id = "umsg-1"
    return resp


# =============================================================================
# handle_chat_respond
# =============================================================================


class TestHandleChatRespond:
    """handle_chat_respond sends text to ChatAgent and returns a structured result."""

    def test_returns_answer_from_agent(self) -> None:
        from cairn.rpc_handlers.chat import handle_chat_respond

        fake_response = _make_agent_response(answer="I can help with that.")
        fake_agent = MagicMock()
        fake_agent.respond.return_value = fake_response
        fake_agent.detect_intent.return_value = None

        with patch("cairn.rpc_handlers.chat.ChatAgent", return_value=fake_agent):
            result = handle_chat_respond(_mock_db(), text="Hello agent")

        assert result["answer"] == "I can help with that."
        assert result["conversation_id"] == "conv-1"
        assert result["message_id"] == "msg-1"

    def test_passes_text_and_optional_params_to_agent(self) -> None:
        from cairn.rpc_handlers.chat import handle_chat_respond

        fake_response = _make_agent_response()
        fake_agent = MagicMock()
        fake_agent.respond.return_value = fake_response
        fake_agent.detect_intent.return_value = None

        with patch("cairn.rpc_handlers.chat.ChatAgent", return_value=fake_agent):
            handle_chat_respond(
                _mock_db(),
                text="Do something",
                conversation_id="conv-99",
                agent_type="cairn",
            )

        fake_agent.respond.assert_called_once_with(
            "Do something",
            conversation_id="conv-99",
            agent_type="cairn",
            extended_thinking=None,
        )

    def test_returns_expected_response_keys(self) -> None:
        from cairn.rpc_handlers.chat import handle_chat_respond

        fake_response = _make_agent_response()
        fake_agent = MagicMock()
        fake_agent.respond.return_value = fake_response
        fake_agent.detect_intent.return_value = None

        with patch("cairn.rpc_handlers.chat.ChatAgent", return_value=fake_agent):
            result = handle_chat_respond(_mock_db(), text="hi")

        for key in ("answer", "conversation_id", "message_id", "message_type", "tool_calls"):
            assert key in result, f"Missing key: {key}"

    def test_handles_intent_detection_returning_none(self) -> None:
        from cairn.rpc_handlers.chat import handle_chat_respond

        fake_response = _make_agent_response()
        fake_agent = MagicMock()
        fake_agent.respond.return_value = fake_response
        fake_agent.detect_intent.return_value = None

        with patch("cairn.rpc_handlers.chat.ChatAgent", return_value=fake_agent):
            result = handle_chat_respond(
                _mock_db(), text="what's up?", conversation_id="conv-1"
            )

        assert result["answer"] == "Hello!"


# =============================================================================
# handle_conversations_list
# =============================================================================


class TestHandleConversationsList:
    """handle_conversations_list returns recent conversations."""

    def test_returns_empty_list_when_no_conversations(self) -> None:
        from cairn.rpc_handlers.chat import handle_conversations_list

        db = _mock_db()
        result = handle_conversations_list(db)

        assert result == {"conversations": []}

    def test_returns_conversations_from_db(self) -> None:
        from cairn.rpc_handlers.chat import handle_conversations_list

        db = _mock_db()
        db.iter_conversations.return_value = [{"id": "conv-1", "title": "First chat"}]

        result = handle_conversations_list(db)

        assert len(result["conversations"]) == 1
        assert result["conversations"][0]["id"] == "conv-1"

    def test_passes_limit_to_db(self) -> None:
        from cairn.rpc_handlers.chat import handle_conversations_list

        db = _mock_db()
        handle_conversations_list(db, limit=5)

        db.iter_conversations.assert_called_once_with(limit=5)

    def test_default_limit_is_20(self) -> None:
        from cairn.rpc_handlers.chat import handle_conversations_list

        db = _mock_db()
        handle_conversations_list(db)

        db.iter_conversations.assert_called_once_with(limit=20)


# =============================================================================
# handle_conversation_messages
# =============================================================================


class TestHandleConversationMessages:
    """handle_conversation_messages returns messages for a conversation."""

    def test_returns_messages_and_conversation_id(self) -> None:
        from cairn.rpc_handlers.chat import handle_conversation_messages

        db = _mock_db()
        db.get_messages.return_value = [{"id": "msg-1", "role": "user", "content": "hi"}]

        result = handle_conversation_messages(db, conversation_id="conv-1")

        assert result["conversation_id"] == "conv-1"
        assert len(result["messages"]) == 1

    def test_returns_empty_messages_when_conversation_is_empty(self) -> None:
        from cairn.rpc_handlers.chat import handle_conversation_messages

        db = _mock_db()
        result = handle_conversation_messages(db, conversation_id="conv-empty")

        assert result["messages"] == []

    def test_passes_conversation_id_and_limit_to_db(self) -> None:
        from cairn.rpc_handlers.chat import handle_conversation_messages

        db = _mock_db()
        handle_conversation_messages(db, conversation_id="conv-x", limit=10)

        db.get_messages.assert_called_once_with(conversation_id="conv-x", limit=10)


# =============================================================================
# handle_chat_clear
# =============================================================================


class TestHandleChatClear:
    """handle_chat_clear deletes messages and the conversation record."""

    def test_returns_ok_true(self) -> None:
        from cairn.rpc_handlers.chat import handle_chat_clear

        db = _mock_db()
        fake_conn = MagicMock()
        db.transaction.return_value.__enter__.return_value = fake_conn

        result = handle_chat_clear(db, conversation_id="conv-del")

        assert result == {"ok": True}

    def test_calls_clear_messages_with_conversation_id(self) -> None:
        from cairn.rpc_handlers.chat import handle_chat_clear

        db = _mock_db()
        fake_conn = MagicMock()
        db.transaction.return_value.__enter__.return_value = fake_conn

        handle_chat_clear(db, conversation_id="conv-del")

        db.clear_messages.assert_called_once_with(conversation_id="conv-del")

    def test_deletes_conversation_row_via_transaction(self) -> None:
        from cairn.rpc_handlers.chat import handle_chat_clear

        db = _mock_db()
        fake_conn = MagicMock()
        db.transaction.return_value.__enter__.return_value = fake_conn

        handle_chat_clear(db, conversation_id="conv-del")

        fake_conn.execute.assert_called_once()
        sql_arg = fake_conn.execute.call_args[0][0]
        assert "DELETE FROM conversations" in sql_arg
