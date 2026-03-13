"""Unit tests for the cc/ RPC handler functions (src/cairn/rpc_handlers/cc.py).

Each handler is tested with a mocked CCManager so tests only verify that:
- the handler delegates to the manager correctly
- parameters are extracted and forwarded
- return values are wrapped as documented

No real DB, no real subprocess.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def run(coro):
    """Run a coroutine synchronously. Used because pytest-asyncio is not installed."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# =============================================================================
# Helpers
# =============================================================================

def _mock_db() -> MagicMock:
    """Return a dummy Database object (handlers only use it as a pass-through)."""
    return MagicMock()


def _make_manager() -> MagicMock:
    """Return a MagicMock that stands in for CCManager."""
    return MagicMock()


# =============================================================================
# handle_cc_agents_list
# =============================================================================


class TestHandleCcAgentsList:
    """handle_cc_agents_list delegates to manager.list_agents using $USER."""

    def test_returns_agents_key_wrapping_manager_result(self) -> None:
        from cairn.rpc_handlers.cc import handle_cc_agents_list

        fake_agents = [{"id": "abc", "name": "Bot"}]
        mgr = _make_manager()
        mgr.list_agents.return_value = fake_agents

        with patch("cairn.rpc_handlers.cc._get_manager", return_value=mgr):
            with patch.dict("os.environ", {"USER": "alice"}):
                result = handle_cc_agents_list(_mock_db())

        assert result == {"agents": fake_agents}

    def test_passes_username_from_env(self) -> None:
        from cairn.rpc_handlers.cc import handle_cc_agents_list

        mgr = _make_manager()
        mgr.list_agents.return_value = []

        with patch("cairn.rpc_handlers.cc._get_manager", return_value=mgr):
            with patch.dict("os.environ", {"USER": "bob"}):
                handle_cc_agents_list(_mock_db())

        mgr.list_agents.assert_called_once_with("bob")

    def test_falls_back_to_unknown_when_user_env_unset(self) -> None:
        from cairn.rpc_handlers.cc import handle_cc_agents_list

        mgr = _make_manager()
        mgr.list_agents.return_value = []

        with patch("cairn.rpc_handlers.cc._get_manager", return_value=mgr):
            with patch.dict("os.environ", {}, clear=True):
                handle_cc_agents_list(_mock_db())

        mgr.list_agents.assert_called_once_with("unknown")

    def test_returns_empty_agents_list_when_none_exist(self) -> None:
        from cairn.rpc_handlers.cc import handle_cc_agents_list

        mgr = _make_manager()
        mgr.list_agents.return_value = []

        with patch("cairn.rpc_handlers.cc._get_manager", return_value=mgr):
            result = handle_cc_agents_list(_mock_db())

        assert result == {"agents": []}


# =============================================================================
# handle_cc_agents_create
# =============================================================================


class TestHandleCcAgentsCreate:
    """handle_cc_agents_create wraps manager.create_agent result in {agent: ...}."""

    def test_returns_agent_key_wrapping_manager_result(self) -> None:
        from cairn.rpc_handlers.cc import handle_cc_agents_create

        fake_agent = {"id": "xyz", "name": "My Bot", "slug": "my-bot", "purpose": ""}
        mgr = _make_manager()
        mgr.create_agent.return_value = fake_agent

        with patch("cairn.rpc_handlers.cc._get_manager", return_value=mgr):
            with patch.dict("os.environ", {"USER": "alice"}):
                result = handle_cc_agents_create(_mock_db(), name="My Bot")

        assert result == {"agent": fake_agent}

    def test_passes_name_and_purpose_to_manager(self) -> None:
        from cairn.rpc_handlers.cc import handle_cc_agents_create

        mgr = _make_manager()
        mgr.create_agent.return_value = {}

        with patch("cairn.rpc_handlers.cc._get_manager", return_value=mgr):
            with patch.dict("os.environ", {"USER": "alice"}):
                handle_cc_agents_create(_mock_db(), name="Bot", purpose="write code")

        mgr.create_agent.assert_called_once_with("alice", "Bot", "write code")

    def test_purpose_defaults_to_empty_string(self) -> None:
        from cairn.rpc_handlers.cc import handle_cc_agents_create

        mgr = _make_manager()
        mgr.create_agent.return_value = {}

        with patch("cairn.rpc_handlers.cc._get_manager", return_value=mgr):
            with patch.dict("os.environ", {"USER": "alice"}):
                handle_cc_agents_create(_mock_db(), name="Bot")

        mgr.create_agent.assert_called_once_with("alice", "Bot", "")

    def test_propagates_rpc_error_from_manager(self) -> None:
        from cairn.rpc_handlers import RpcError
        from cairn.rpc_handlers.cc import handle_cc_agents_create

        mgr = _make_manager()
        mgr.create_agent.side_effect = RpcError(code=-32000, message="slug conflict")

        with patch("cairn.rpc_handlers.cc._get_manager", return_value=mgr):
            with pytest.raises(RpcError):
                handle_cc_agents_create(_mock_db(), name="Bot")


# =============================================================================
# handle_cc_agents_delete
# =============================================================================


class TestHandleCcAgentsDelete:
    """handle_cc_agents_delete delegates to manager.delete_agent and returns its result."""

    def test_returns_ok_true_on_success(self) -> None:
        from cairn.rpc_handlers.cc import handle_cc_agents_delete

        mgr = _make_manager()
        mgr.delete_agent.return_value = {"ok": True}

        with patch("cairn.rpc_handlers.cc._get_manager", return_value=mgr):
            result = handle_cc_agents_delete(_mock_db(), agent_id="abc-123")

        assert result == {"ok": True}

    def test_passes_agent_id_to_manager(self) -> None:
        from cairn.rpc_handlers.cc import handle_cc_agents_delete

        mgr = _make_manager()
        mgr.delete_agent.return_value = {"ok": True}

        with patch("cairn.rpc_handlers.cc._get_manager", return_value=mgr):
            handle_cc_agents_delete(_mock_db(), agent_id="my-agent-id")

        mgr.delete_agent.assert_called_once_with("my-agent-id")

    def test_propagates_rpc_error_when_agent_not_found(self) -> None:
        from cairn.rpc_handlers import RpcError
        from cairn.rpc_handlers.cc import handle_cc_agents_delete

        mgr = _make_manager()
        mgr.delete_agent.side_effect = RpcError(code=-32003, message="Agent not found")

        with patch("cairn.rpc_handlers.cc._get_manager", return_value=mgr):
            with pytest.raises(RpcError) as exc_info:
                handle_cc_agents_delete(_mock_db(), agent_id="missing")

        assert exc_info.value.code == -32003


# =============================================================================
# handle_cc_session_send
# =============================================================================


class TestHandleCcSessionSend:
    """handle_cc_session_send is async and delegates to manager.send_message."""

    def test_returns_manager_result(self) -> None:
        from cairn.rpc_handlers.cc import handle_cc_session_send

        fake_result = {"agent_id": "abc", "status": "accepted"}
        mgr = _make_manager()
        mgr.send_message = AsyncMock(return_value=fake_result)

        with patch("cairn.rpc_handlers.cc._get_manager", return_value=mgr):
            result = run(handle_cc_session_send(_mock_db(), agent_id="abc", text="hello"))

        assert result == fake_result

    def test_passes_agent_id_and_text_to_manager(self) -> None:
        from cairn.rpc_handlers.cc import handle_cc_session_send

        mgr = _make_manager()
        mgr.send_message = AsyncMock(return_value={"agent_id": "x", "status": "accepted"})

        with patch("cairn.rpc_handlers.cc._get_manager", return_value=mgr):
            run(handle_cc_session_send(_mock_db(), agent_id="agent-id-1", text="do something"))

        mgr.send_message.assert_awaited_once_with("agent-id-1", "do something")

    def test_propagates_rpc_error_for_missing_agent(self) -> None:
        from cairn.rpc_handlers import RpcError
        from cairn.rpc_handlers.cc import handle_cc_session_send

        mgr = _make_manager()
        mgr.send_message = AsyncMock(side_effect=RpcError(code=-32003, message="Agent not found"))

        with patch("cairn.rpc_handlers.cc._get_manager", return_value=mgr):
            with pytest.raises(RpcError) as exc_info:
                run(handle_cc_session_send(_mock_db(), agent_id="bad-id", text="hi"))

        assert exc_info.value.code == -32003

    def test_propagates_rpc_error_for_busy_agent(self) -> None:
        from cairn.rpc_handlers import RpcError
        from cairn.rpc_handlers.cc import handle_cc_session_send

        mgr = _make_manager()
        mgr.send_message = AsyncMock(side_effect=RpcError(code=-32000, message="Agent is busy"))

        with patch("cairn.rpc_handlers.cc._get_manager", return_value=mgr):
            with pytest.raises(RpcError) as exc_info:
                run(handle_cc_session_send(_mock_db(), agent_id="agent-id", text="hi"))

        assert exc_info.value.code == -32000


# =============================================================================
# handle_cc_session_poll
# =============================================================================


class TestHandleCcSessionPoll:
    """handle_cc_session_poll delegates to manager.poll_events."""

    def test_returns_manager_poll_result(self) -> None:
        from cairn.rpc_handlers.cc import handle_cc_session_poll

        fake_result = {"events": [], "next_index": 0, "busy": False}
        mgr = _make_manager()
        mgr.poll_events.return_value = fake_result

        with patch("cairn.rpc_handlers.cc._get_manager", return_value=mgr):
            result = handle_cc_session_poll(_mock_db(), agent_id="abc", since=0)

        assert result == fake_result

    def test_passes_agent_id_and_since_to_manager(self) -> None:
        from cairn.rpc_handlers.cc import handle_cc_session_poll

        mgr = _make_manager()
        mgr.poll_events.return_value = {"events": [], "next_index": 5, "busy": False}

        with patch("cairn.rpc_handlers.cc._get_manager", return_value=mgr):
            handle_cc_session_poll(_mock_db(), agent_id="agent-42", since=5)

        mgr.poll_events.assert_called_once_with("agent-42", 5)

    def test_since_defaults_to_zero(self) -> None:
        from cairn.rpc_handlers.cc import handle_cc_session_poll

        mgr = _make_manager()
        mgr.poll_events.return_value = {"events": [], "next_index": 0, "busy": False}

        with patch("cairn.rpc_handlers.cc._get_manager", return_value=mgr):
            handle_cc_session_poll(_mock_db(), agent_id="agent-1")

        mgr.poll_events.assert_called_once_with("agent-1", 0)


# =============================================================================
# handle_cc_session_stop
# =============================================================================


class TestHandleCcSessionStop:
    """handle_cc_session_stop is async and delegates to manager.stop_session."""

    def test_returns_ok_true(self) -> None:
        from cairn.rpc_handlers.cc import handle_cc_session_stop

        mgr = _make_manager()
        mgr.stop_session = AsyncMock(return_value={"ok": True})

        with patch("cairn.rpc_handlers.cc._get_manager", return_value=mgr):
            result = run(handle_cc_session_stop(_mock_db(), agent_id="abc"))

        assert result == {"ok": True}

    def test_passes_agent_id_to_manager(self) -> None:
        from cairn.rpc_handlers.cc import handle_cc_session_stop

        mgr = _make_manager()
        mgr.stop_session = AsyncMock(return_value={"ok": True})

        with patch("cairn.rpc_handlers.cc._get_manager", return_value=mgr):
            run(handle_cc_session_stop(_mock_db(), agent_id="my-agent"))

        mgr.stop_session.assert_awaited_once_with("my-agent")

    def test_returns_ok_true_when_no_process_was_running(self) -> None:
        from cairn.rpc_handlers.cc import handle_cc_session_stop

        mgr = _make_manager()
        mgr.stop_session = AsyncMock(return_value={"ok": True})

        with patch("cairn.rpc_handlers.cc._get_manager", return_value=mgr):
            result = run(handle_cc_session_stop(_mock_db(), agent_id="idle-agent"))

        assert result["ok"] is True


# =============================================================================
# handle_cc_session_history
# =============================================================================


class TestHandleCcSessionHistory:
    """handle_cc_session_history delegates to manager.get_history."""

    def test_returns_messages_key_wrapping_history(self) -> None:
        from cairn.rpc_handlers.cc import handle_cc_session_history

        fake_messages = [
            {"role": "user", "content": "hello", "created_at": "2026-01-01T00:00:00Z"},
        ]
        mgr = _make_manager()
        mgr.get_history.return_value = fake_messages

        with patch("cairn.rpc_handlers.cc._get_manager", return_value=mgr):
            result = handle_cc_session_history(_mock_db(), agent_id="abc")

        assert result == {"messages": fake_messages}

    def test_passes_agent_id_and_limit_to_manager(self) -> None:
        from cairn.rpc_handlers.cc import handle_cc_session_history

        mgr = _make_manager()
        mgr.get_history.return_value = []

        with patch("cairn.rpc_handlers.cc._get_manager", return_value=mgr):
            handle_cc_session_history(_mock_db(), agent_id="agent-1", limit=50)

        mgr.get_history.assert_called_once_with("agent-1", 50)

    def test_limit_defaults_to_100(self) -> None:
        from cairn.rpc_handlers.cc import handle_cc_session_history

        mgr = _make_manager()
        mgr.get_history.return_value = []

        with patch("cairn.rpc_handlers.cc._get_manager", return_value=mgr):
            handle_cc_session_history(_mock_db(), agent_id="agent-1")

        mgr.get_history.assert_called_once_with("agent-1", 100)

    def test_returns_empty_messages_when_no_history(self) -> None:
        from cairn.rpc_handlers.cc import handle_cc_session_history

        mgr = _make_manager()
        mgr.get_history.return_value = []

        with patch("cairn.rpc_handlers.cc._get_manager", return_value=mgr):
            result = handle_cc_session_history(_mock_db(), agent_id="new-agent")

        assert result == {"messages": []}


# =============================================================================
# _get_manager singleton
# =============================================================================


class TestGetManagerSingleton:
    """_get_manager returns the same instance across calls."""

    def test_returns_ccmanager_instance(self) -> None:
        import cairn.rpc_handlers.cc as cc_mod
        from cairn.services.cc_manager import CCManager

        # Reset singleton between tests to avoid cross-test contamination
        original = cc_mod._manager
        cc_mod._manager = None
        try:
            mgr = cc_mod._get_manager()
            assert isinstance(mgr, CCManager)
        finally:
            cc_mod._manager = original

    def test_returns_same_instance_on_repeated_calls(self) -> None:
        import cairn.rpc_handlers.cc as cc_mod

        original = cc_mod._manager
        cc_mod._manager = None
        try:
            mgr1 = cc_mod._get_manager()
            mgr2 = cc_mod._get_manager()
            assert mgr1 is mgr2
        finally:
            cc_mod._manager = original
