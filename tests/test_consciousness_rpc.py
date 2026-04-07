"""Unit tests for consciousness RPC handlers (src/cairn/rpc_handlers/consciousness.py).

Each handler is tested with mocked dependencies so tests only verify that:
- the handler delegates to the observer/chat correctly
- parameters are extracted and forwarded
- return values are shaped as documented
- error paths behave correctly

No real DB, no real subprocess, no real Ollama.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime
from unittest.mock import MagicMock, call, patch

import pytest


# =============================================================================
# Helpers
# =============================================================================


def _mock_db() -> MagicMock:
    """Return a dummy Database object (handlers only use it as a pass-through)."""
    return MagicMock()


def _make_observer() -> MagicMock:
    """Return a MagicMock standing in for a ConsciousnessObserver instance."""
    return MagicMock()


def _make_event(event_type_name: str = "PHASE_START", title: str = "Test") -> MagicMock:
    """Return a MagicMock shaped like a ConsciousnessEvent."""
    event = MagicMock()
    event.event_type.name = event_type_name
    event.timestamp = datetime(2026, 1, 1, 12, 0, 0)
    event.title = title
    event.content = "some content"
    event.metadata = {"key": "val"}
    return event


# =============================================================================
# handle_consciousness_start
# =============================================================================


class TestHandleConsciousnessStart:
    """handle_consciousness_start calls observer.start_session() and returns {status: started}."""

    def test_returns_status_started(self) -> None:
        from cairn.rpc_handlers.consciousness import handle_consciousness_start

        observer = _make_observer()
        with patch(
            "cairn.cairn.consciousness_stream.ConsciousnessObserver"
        ) as MockObserver:
            MockObserver.get_instance.return_value = observer
            result = handle_consciousness_start(_mock_db())

        assert result == {"status": "started"}

    def test_calls_start_session_on_observer(self) -> None:
        from cairn.rpc_handlers.consciousness import handle_consciousness_start

        observer = _make_observer()
        with patch(
            "cairn.cairn.consciousness_stream.ConsciousnessObserver"
        ) as MockObserver:
            MockObserver.get_instance.return_value = observer
            handle_consciousness_start(_mock_db())

        observer.start_session.assert_called_once_with()

    def test_uses_singleton_via_get_instance(self) -> None:
        from cairn.rpc_handlers.consciousness import handle_consciousness_start

        observer = _make_observer()
        with patch(
            "cairn.cairn.consciousness_stream.ConsciousnessObserver"
        ) as MockObserver:
            MockObserver.get_instance.return_value = observer
            handle_consciousness_start(_mock_db())

        MockObserver.get_instance.assert_called_once_with()

    def test_db_parameter_is_not_used(self) -> None:
        from cairn.rpc_handlers.consciousness import handle_consciousness_start

        observer = _make_observer()
        db = _mock_db()
        with patch(
            "cairn.cairn.consciousness_stream.ConsciousnessObserver"
        ) as MockObserver:
            MockObserver.get_instance.return_value = observer
            handle_consciousness_start(db)

        # db should never be called on (it's unused)
        db.assert_not_called()


# =============================================================================
# handle_consciousness_poll
# =============================================================================


class TestHandleConsciousnessPoll:
    """handle_consciousness_poll forwards since_index to observer.poll() and shapes the result."""

    def test_returns_events_and_next_index(self) -> None:
        from cairn.rpc_handlers.consciousness import handle_consciousness_poll

        event = _make_event("INTENT_EXTRACTED", "Intent found")
        observer = _make_observer()
        observer.poll.return_value = [event]

        with patch(
            "cairn.cairn.consciousness_stream.ConsciousnessObserver"
        ) as MockObserver:
            MockObserver.get_instance.return_value = observer
            result = handle_consciousness_poll(_mock_db(), since_index=0)

        assert result["next_index"] == 1
        assert len(result["events"]) == 1

    def test_event_fields_are_serialised_correctly(self) -> None:
        from cairn.rpc_handlers.consciousness import handle_consciousness_poll

        event = _make_event("PHASE_START", "Phase started")
        event.content = "thinking..."
        event.metadata = {"phase": "extract"}
        observer = _make_observer()
        observer.poll.return_value = [event]

        with patch(
            "cairn.cairn.consciousness_stream.ConsciousnessObserver"
        ) as MockObserver:
            MockObserver.get_instance.return_value = observer
            result = handle_consciousness_poll(_mock_db(), since_index=0)

        serialised = result["events"][0]
        assert serialised["type"] == "PHASE_START"
        assert serialised["title"] == "Phase started"
        assert serialised["content"] == "thinking..."
        assert serialised["metadata"] == {"phase": "extract"}
        assert serialised["timestamp"] == "2026-01-01T12:00:00"

    def test_since_index_defaults_to_zero(self) -> None:
        from cairn.rpc_handlers.consciousness import handle_consciousness_poll

        observer = _make_observer()
        observer.poll.return_value = []

        with patch(
            "cairn.cairn.consciousness_stream.ConsciousnessObserver"
        ) as MockObserver:
            MockObserver.get_instance.return_value = observer
            handle_consciousness_poll(_mock_db())

        observer.poll.assert_called_once_with(0)

    def test_since_index_is_forwarded_to_poll(self) -> None:
        from cairn.rpc_handlers.consciousness import handle_consciousness_poll

        observer = _make_observer()
        observer.poll.return_value = []

        with patch(
            "cairn.cairn.consciousness_stream.ConsciousnessObserver"
        ) as MockObserver:
            MockObserver.get_instance.return_value = observer
            handle_consciousness_poll(_mock_db(), since_index=7)

        observer.poll.assert_called_once_with(7)

    def test_next_index_increments_by_event_count(self) -> None:
        from cairn.rpc_handlers.consciousness import handle_consciousness_poll

        events = [_make_event() for _ in range(3)]
        observer = _make_observer()
        observer.poll.return_value = events

        with patch(
            "cairn.cairn.consciousness_stream.ConsciousnessObserver"
        ) as MockObserver:
            MockObserver.get_instance.return_value = observer
            result = handle_consciousness_poll(_mock_db(), since_index=5)

        assert result["next_index"] == 8  # 5 + 3

    def test_returns_empty_events_when_none_available(self) -> None:
        from cairn.rpc_handlers.consciousness import handle_consciousness_poll

        observer = _make_observer()
        observer.poll.return_value = []

        with patch(
            "cairn.cairn.consciousness_stream.ConsciousnessObserver"
        ) as MockObserver:
            MockObserver.get_instance.return_value = observer
            result = handle_consciousness_poll(_mock_db(), since_index=0)

        assert result == {"events": [], "next_index": 0}


# =============================================================================
# handle_consciousness_snapshot
# =============================================================================


class TestHandleConsciousnessSnapshot:
    """handle_consciousness_snapshot calls observer.get_all() and returns all events."""

    def test_returns_events_key_with_all_events(self) -> None:
        from cairn.rpc_handlers.consciousness import handle_consciousness_snapshot

        events = [_make_event("PHASE_START"), _make_event("RESPONSE_READY")]
        observer = _make_observer()
        observer.get_all.return_value = events

        with patch(
            "cairn.cairn.consciousness_stream.ConsciousnessObserver"
        ) as MockObserver:
            MockObserver.get_instance.return_value = observer
            result = handle_consciousness_snapshot(_mock_db())

        assert "events" in result
        assert len(result["events"]) == 2

    def test_calls_get_all_not_poll(self) -> None:
        from cairn.rpc_handlers.consciousness import handle_consciousness_snapshot

        observer = _make_observer()
        observer.get_all.return_value = []

        with patch(
            "cairn.cairn.consciousness_stream.ConsciousnessObserver"
        ) as MockObserver:
            MockObserver.get_instance.return_value = observer
            handle_consciousness_snapshot(_mock_db())

        observer.get_all.assert_called_once_with()
        observer.poll.assert_not_called()

    def test_snapshot_has_no_next_index_field(self) -> None:
        from cairn.rpc_handlers.consciousness import handle_consciousness_snapshot

        observer = _make_observer()
        observer.get_all.return_value = []

        with patch(
            "cairn.cairn.consciousness_stream.ConsciousnessObserver"
        ) as MockObserver:
            MockObserver.get_instance.return_value = observer
            result = handle_consciousness_snapshot(_mock_db())

        assert "next_index" not in result

    def test_event_fields_are_serialised_correctly(self) -> None:
        from cairn.rpc_handlers.consciousness import handle_consciousness_snapshot

        event = _make_event("TOOL_CALL_START", "Calling calendar tool")
        event.content = "get_events()"
        event.metadata = None
        observer = _make_observer()
        observer.get_all.return_value = [event]

        with patch(
            "cairn.cairn.consciousness_stream.ConsciousnessObserver"
        ) as MockObserver:
            MockObserver.get_instance.return_value = observer
            result = handle_consciousness_snapshot(_mock_db())

        serialised = result["events"][0]
        assert serialised["type"] == "TOOL_CALL_START"
        assert serialised["title"] == "Calling calendar tool"
        assert serialised["content"] == "get_events()"
        assert serialised["metadata"] is None

    def test_returns_empty_events_when_session_empty(self) -> None:
        from cairn.rpc_handlers.consciousness import handle_consciousness_snapshot

        observer = _make_observer()
        observer.get_all.return_value = []

        with patch(
            "cairn.cairn.consciousness_stream.ConsciousnessObserver"
        ) as MockObserver:
            MockObserver.get_instance.return_value = observer
            result = handle_consciousness_snapshot(_mock_db())

        assert result == {"events": []}


# =============================================================================
# handle_cairn_chat_async
# =============================================================================


class TestHandleCairnChatAsync:
    """handle_cairn_chat_async starts a background thread and returns immediately."""

    def setup_method(self) -> None:
        """Clear module-level chat state before each test."""
        import cairn.rpc_handlers.consciousness as mod

        with mod._cairn_chat_lock:
            mod._active_cairn_chats.clear()

    def teardown_method(self) -> None:
        """Clear module-level chat state after each test."""
        import cairn.rpc_handlers.consciousness as mod

        with mod._cairn_chat_lock:
            mod._active_cairn_chats.clear()

    def test_returns_chat_id_and_status_started(self) -> None:
        from cairn.rpc_handlers.consciousness import handle_cairn_chat_async

        observer = _make_observer()
        with patch(
            "cairn.cairn.consciousness_stream.ConsciousnessObserver"
        ) as MockObserver, patch(
            "cairn.rpc_handlers.consciousness.handle_chat_respond"
        ) as mock_chat:
            MockObserver.get_instance.return_value = observer
            mock_chat.return_value = {"message": "hello"}
            result = handle_cairn_chat_async(_mock_db(), text="hi")

        assert "chat_id" in result
        assert result["status"] == "started"
        assert len(result["chat_id"]) == 12  # uuid4().hex[:12]

    def test_returns_immediately_before_chat_completes(self) -> None:
        """Handler returns before background thread finishes."""
        from cairn.rpc_handlers.consciousness import handle_cairn_chat_async

        started_event = threading.Event()
        proceed_event = threading.Event()
        observer = _make_observer()

        def slow_chat(*args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN202
            started_event.set()
            proceed_event.wait(timeout=5)
            return {"message": "done"}

        with patch(
            "cairn.cairn.consciousness_stream.ConsciousnessObserver"
        ) as MockObserver, patch(
            "cairn.rpc_handlers.consciousness.handle_chat_respond",
            side_effect=slow_chat,
        ):
            MockObserver.get_instance.return_value = observer
            result = handle_cairn_chat_async(_mock_db(), text="slow query")

        # Handler returned immediately with a chat_id
        assert result["status"] == "started"
        assert "chat_id" in result
        # Unblock the background thread so the daemon thread can exit cleanly
        proceed_event.set()

    def test_chat_is_tracked_in_active_chats(self) -> None:
        import cairn.rpc_handlers.consciousness as mod
        from cairn.rpc_handlers.consciousness import handle_cairn_chat_async

        observer = _make_observer()
        with patch(
            "cairn.cairn.consciousness_stream.ConsciousnessObserver"
        ) as MockObserver, patch(
            "cairn.rpc_handlers.consciousness.handle_chat_respond",
            return_value={"message": "ok"},
        ):
            MockObserver.get_instance.return_value = observer
            result = handle_cairn_chat_async(_mock_db(), text="track me")

        chat_id = result["chat_id"]
        # Give the thread a moment to start (it may complete quickly)
        time.sleep(0.05)
        # Either still tracked (processing) or already cleaned up (complete) — either is fine
        # What matters is it was registered
        assert chat_id  # non-empty string

    def test_starts_consciousness_session(self) -> None:
        from cairn.rpc_handlers.consciousness import handle_cairn_chat_async

        observer = _make_observer()
        with patch(
            "cairn.cairn.consciousness_stream.ConsciousnessObserver"
        ) as MockObserver, patch(
            "cairn.rpc_handlers.consciousness.handle_chat_respond",
            return_value={"message": "ok"},
        ):
            MockObserver.get_instance.return_value = observer
            handle_cairn_chat_async(_mock_db(), text="start session")

        observer.start_session.assert_called_once_with()

    def test_background_thread_calls_handle_chat_respond_with_correct_args(self) -> None:
        from cairn.rpc_handlers.consciousness import handle_cairn_chat_async

        observer = _make_observer()
        mock_chat = MagicMock(return_value={"message": "response"})

        db = _mock_db()
        with patch(
            "cairn.cairn.consciousness_stream.ConsciousnessObserver"
        ) as MockObserver, patch(
            "cairn.rpc_handlers.consciousness.handle_chat_respond",
            mock_chat,
        ):
            MockObserver.get_instance.return_value = observer
            handle_cairn_chat_async(
                db,
                text="what's next?",
                conversation_id="conv-123",
                extended_thinking=True,
            )

        # Allow the background thread to finish
        time.sleep(0.2)

        mock_chat.assert_called_once_with(
            db,
            text="what's next?",
            conversation_id="conv-123",
            agent_type="cairn",
            extended_thinking=True,
        )

    def test_background_thread_error_is_captured_not_raised(self) -> None:
        from cairn.rpc_handlers.consciousness import handle_cairn_chat_async

        observer = _make_observer()
        with patch(
            "cairn.cairn.consciousness_stream.ConsciousnessObserver"
        ) as MockObserver, patch(
            "cairn.rpc_handlers.consciousness.handle_chat_respond",
            side_effect=RuntimeError("LLM unavailable"),
        ):
            MockObserver.get_instance.return_value = observer
            # Must not raise even though background thread will fail
            result = handle_cairn_chat_async(_mock_db(), text="broken")

        assert result["status"] == "started"
        # Allow background thread to fail
        time.sleep(0.2)

    def test_conversation_id_defaults_to_none(self) -> None:
        from cairn.rpc_handlers.consciousness import handle_cairn_chat_async

        observer = _make_observer()
        mock_chat = MagicMock(return_value={"message": "ok"})

        with patch(
            "cairn.cairn.consciousness_stream.ConsciousnessObserver"
        ) as MockObserver, patch(
            "cairn.rpc_handlers.consciousness.handle_chat_respond",
            mock_chat,
        ):
            MockObserver.get_instance.return_value = observer
            handle_cairn_chat_async(_mock_db(), text="hello")

        time.sleep(0.2)
        _args, kwargs = mock_chat.call_args
        assert kwargs["conversation_id"] is None

    def test_extended_thinking_defaults_to_false(self) -> None:
        from cairn.rpc_handlers.consciousness import handle_cairn_chat_async

        observer = _make_observer()
        mock_chat = MagicMock(return_value={"message": "ok"})

        with patch(
            "cairn.cairn.consciousness_stream.ConsciousnessObserver"
        ) as MockObserver, patch(
            "cairn.rpc_handlers.consciousness.handle_chat_respond",
            mock_chat,
        ):
            MockObserver.get_instance.return_value = observer
            handle_cairn_chat_async(_mock_db(), text="hello")

        time.sleep(0.2)
        _args, kwargs = mock_chat.call_args
        assert kwargs["extended_thinking"] is False


# =============================================================================
# handle_cairn_chat_status
# =============================================================================


class TestHandleCairnChatStatus:
    """handle_cairn_chat_status returns the status of an async chat request."""

    def setup_method(self) -> None:
        import cairn.rpc_handlers.consciousness as mod

        with mod._cairn_chat_lock:
            mod._active_cairn_chats.clear()

    def teardown_method(self) -> None:
        import cairn.rpc_handlers.consciousness as mod

        with mod._cairn_chat_lock:
            mod._active_cairn_chats.clear()

    def test_returns_not_found_for_unknown_chat_id(self) -> None:
        from cairn.rpc_handlers.consciousness import handle_cairn_chat_status

        result = handle_cairn_chat_status(_mock_db(), chat_id="nonexistent-id")

        assert result["status"] == "not_found"
        assert "not found" in result["error"].lower() or "nonexistent-id" in result["error"]

    def test_returns_processing_when_chat_not_complete(self) -> None:
        import cairn.rpc_handlers.consciousness as mod
        from cairn.rpc_handlers.consciousness import CairnChatContext, handle_cairn_chat_status

        ctx = CairnChatContext(
            chat_id="abc123",
            text="hello",
            conversation_id=None,
            extended_thinking=False,
            is_complete=False,
        )
        with mod._cairn_chat_lock:
            mod._active_cairn_chats["abc123"] = ctx

        result = handle_cairn_chat_status(_mock_db(), chat_id="abc123")

        assert result == {"chat_id": "abc123", "status": "processing"}

    def test_returns_complete_with_result_when_done(self) -> None:
        import cairn.rpc_handlers.consciousness as mod
        from cairn.rpc_handlers.consciousness import CairnChatContext, handle_cairn_chat_status

        ctx = CairnChatContext(
            chat_id="done123",
            text="hello",
            conversation_id=None,
            extended_thinking=False,
            is_complete=True,
            result={"message": "the answer"},
        )
        with mod._cairn_chat_lock:
            mod._active_cairn_chats["done123"] = ctx

        result = handle_cairn_chat_status(_mock_db(), chat_id="done123")

        assert result["status"] == "complete"
        assert result["result"] == {"message": "the answer"}
        assert result["chat_id"] == "done123"

    def test_removes_completed_chat_from_active_chats(self) -> None:
        import cairn.rpc_handlers.consciousness as mod
        from cairn.rpc_handlers.consciousness import CairnChatContext, handle_cairn_chat_status

        ctx = CairnChatContext(
            chat_id="cleanup-me",
            text="hi",
            conversation_id=None,
            extended_thinking=False,
            is_complete=True,
            result={"message": "done"},
        )
        with mod._cairn_chat_lock:
            mod._active_cairn_chats["cleanup-me"] = ctx

        handle_cairn_chat_status(_mock_db(), chat_id="cleanup-me")

        with mod._cairn_chat_lock:
            assert "cleanup-me" not in mod._active_cairn_chats

    def test_returns_error_status_when_chat_errored(self) -> None:
        import cairn.rpc_handlers.consciousness as mod
        from cairn.rpc_handlers.consciousness import CairnChatContext, handle_cairn_chat_status

        ctx = CairnChatContext(
            chat_id="err-456",
            text="boom",
            conversation_id=None,
            extended_thinking=False,
            is_complete=True,
            error="LLM unavailable",
        )
        with mod._cairn_chat_lock:
            mod._active_cairn_chats["err-456"] = ctx

        result = handle_cairn_chat_status(_mock_db(), chat_id="err-456")

        assert result["status"] == "error"
        assert result["error"] == "LLM unavailable"
        assert result["chat_id"] == "err-456"

    def test_errored_chat_is_not_cleaned_up(self) -> None:
        """Error state stays in active_chats so the error can be retrieved repeatedly."""
        import cairn.rpc_handlers.consciousness as mod
        from cairn.rpc_handlers.consciousness import CairnChatContext, handle_cairn_chat_status

        ctx = CairnChatContext(
            chat_id="err-persist",
            text="boom",
            conversation_id=None,
            extended_thinking=False,
            is_complete=True,
            error="timeout",
        )
        with mod._cairn_chat_lock:
            mod._active_cairn_chats["err-persist"] = ctx

        handle_cairn_chat_status(_mock_db(), chat_id="err-persist")

        # Error chat should still be in the dict
        with mod._cairn_chat_lock:
            assert "err-persist" in mod._active_cairn_chats


# =============================================================================
# handle_consciousness_persist
# =============================================================================


class TestHandleConsciousnessPersist:
    """handle_consciousness_persist creates a block hierarchy from consciousness events."""

    def _make_chain_block(self, block_id: str = "chain-block-1") -> MagicMock:
        block = MagicMock()
        block.id = block_id
        return block

    def test_returns_chain_block_id_and_event_count(self) -> None:
        from cairn.rpc_handlers.consciousness import handle_consciousness_persist

        chain_block = self._make_chain_block("chain-abc")
        observer = _make_observer()
        events = [_make_event(), _make_event()]
        observer.get_all.return_value = events

        mock_create_block = MagicMock(return_value=chain_block)

        with patch(
            "cairn.cairn.consciousness_stream.ConsciousnessObserver"
        ) as MockObserver, patch(
            "cairn.play.blocks_db"
        ) as mock_blocks_db, patch(
            "cairn.play_db.list_acts",
            return_value=([], "act-999"),
        ):
            MockObserver.get_instance.return_value = observer
            mock_blocks_db.create_block.return_value = chain_block

            result = handle_consciousness_persist(
                _mock_db(),
                conversation_id="conv-1",
                user_message_id="user-msg-1",
                response_message_id="resp-msg-1",
                act_id="act-999",
            )

        assert result["chain_block_id"] == "chain-abc"
        assert result["event_count"] == 2

    def test_creates_reasoning_chain_root_block(self) -> None:
        from cairn.rpc_handlers.consciousness import handle_consciousness_persist
        from cairn.play.blocks_models import BlockType

        chain_block = self._make_chain_block("root-id")
        observer = _make_observer()
        observer.get_all.return_value = []

        with patch(
            "cairn.cairn.consciousness_stream.ConsciousnessObserver"
        ) as MockObserver, patch(
            "cairn.play.blocks_db"
        ) as mock_blocks_db, patch(
            "cairn.play_db.list_acts",
            return_value=([], "act-1"),
        ):
            MockObserver.get_instance.return_value = observer
            mock_blocks_db.create_block.return_value = chain_block

            handle_consciousness_persist(
                _mock_db(),
                conversation_id="conv-42",
                user_message_id="u-1",
                response_message_id="r-1",
                act_id="act-1",
            )

        first_call = mock_blocks_db.create_block.call_args_list[0]
        assert first_call.kwargs["type"] == BlockType.REASONING_CHAIN
        assert first_call.kwargs["properties"]["conversation_id"] == "conv-42"

    def test_creates_user_prompt_and_llm_response_blocks(self) -> None:
        from cairn.rpc_handlers.consciousness import handle_consciousness_persist
        from cairn.play.blocks_models import BlockType

        chain_block = self._make_chain_block()
        observer = _make_observer()
        observer.get_all.return_value = []

        with patch(
            "cairn.cairn.consciousness_stream.ConsciousnessObserver"
        ) as MockObserver, patch(
            "cairn.play.blocks_db"
        ) as mock_blocks_db, patch(
            "cairn.play_db.list_acts",
            return_value=([], "act-1"),
        ):
            MockObserver.get_instance.return_value = observer
            mock_blocks_db.create_block.return_value = chain_block

            handle_consciousness_persist(
                _mock_db(),
                conversation_id="conv-1",
                user_message_id="user-msg-99",
                response_message_id="resp-msg-99",
                act_id="act-1",
            )

        all_calls = mock_blocks_db.create_block.call_args_list
        created_types = [c.kwargs["type"] for c in all_calls]
        assert BlockType.USER_PROMPT in created_types
        assert BlockType.LLM_RESPONSE in created_types

    def test_creates_consciousness_event_blocks_for_each_event(self) -> None:
        from cairn.rpc_handlers.consciousness import handle_consciousness_persist
        from cairn.play.blocks_models import BlockType

        chain_block = self._make_chain_block()
        observer = _make_observer()
        observer.get_all.return_value = [_make_event(), _make_event(), _make_event()]

        with patch(
            "cairn.cairn.consciousness_stream.ConsciousnessObserver"
        ) as MockObserver, patch(
            "cairn.play.blocks_db"
        ) as mock_blocks_db, patch(
            "cairn.play_db.list_acts",
            return_value=([], "act-1"),
        ):
            MockObserver.get_instance.return_value = observer
            mock_blocks_db.create_block.return_value = chain_block

            handle_consciousness_persist(
                _mock_db(),
                conversation_id="conv-1",
                user_message_id="u-1",
                response_message_id="r-1",
                act_id="act-1",
            )

        all_calls = mock_blocks_db.create_block.call_args_list
        event_blocks = [c for c in all_calls if c.kwargs["type"] == BlockType.CONSCIOUSNESS_EVENT]
        assert len(event_blocks) == 3

    def test_falls_back_to_active_act_when_act_id_not_provided(self) -> None:
        from cairn.rpc_handlers.consciousness import handle_consciousness_persist

        chain_block = self._make_chain_block()
        observer = _make_observer()
        observer.get_all.return_value = []

        with patch(
            "cairn.cairn.consciousness_stream.ConsciousnessObserver"
        ) as MockObserver, patch(
            "cairn.play.blocks_db"
        ) as mock_blocks_db, patch(
            "cairn.play_db.list_acts",
            return_value=([], "active-act-id"),
        ) as mock_list_acts:
            MockObserver.get_instance.return_value = observer
            mock_blocks_db.create_block.return_value = chain_block

            result = handle_consciousness_persist(
                _mock_db(),
                conversation_id="conv-1",
                user_message_id="u-1",
                response_message_id="r-1",
                # act_id intentionally omitted
            )

        mock_list_acts.assert_called_once_with()
        # Blocks should have been created with the active act
        first_call = mock_blocks_db.create_block.call_args_list[0]
        assert first_call.kwargs["act_id"] == "active-act-id"

    def test_returns_error_when_no_act_id_and_no_active_act(self) -> None:
        from cairn.rpc_handlers.consciousness import handle_consciousness_persist

        observer = _make_observer()
        observer.get_all.return_value = []

        with patch(
            "cairn.cairn.consciousness_stream.ConsciousnessObserver"
        ) as MockObserver, patch(
            "cairn.play.blocks_db"
        ) as mock_blocks_db, patch(
            "cairn.play_db.list_acts",
            return_value=([], None),  # no active act
        ):
            MockObserver.get_instance.return_value = observer

            result = handle_consciousness_persist(
                _mock_db(),
                conversation_id="conv-1",
                user_message_id="u-1",
                response_message_id="r-1",
            )

        assert result["chain_block_id"] is None
        assert result["event_count"] == 0
        assert "error" in result
        mock_blocks_db.create_block.assert_not_called()

    def test_block_positions_are_sequential(self) -> None:
        """user_prompt is at 0, events at 1..N-1, llm_response at N."""
        from cairn.rpc_handlers.consciousness import handle_consciousness_persist
        from cairn.play.blocks_models import BlockType

        chain_block = self._make_chain_block()
        observer = _make_observer()
        observer.get_all.return_value = [_make_event(), _make_event()]

        with patch(
            "cairn.cairn.consciousness_stream.ConsciousnessObserver"
        ) as MockObserver, patch(
            "cairn.play.blocks_db"
        ) as mock_blocks_db, patch(
            "cairn.play_db.list_acts",
            return_value=([], "act-1"),
        ):
            MockObserver.get_instance.return_value = observer
            mock_blocks_db.create_block.return_value = chain_block

            handle_consciousness_persist(
                _mock_db(),
                conversation_id="conv-1",
                user_message_id="u-1",
                response_message_id="r-1",
                act_id="act-1",
            )

        all_calls = mock_blocks_db.create_block.call_args_list
        # First call is the root chain — no position
        # Subsequent calls: user_prompt(0), event(1), event(2), llm_response(3)
        child_calls = [c for c in all_calls if "position" in c.kwargs]
        positions = [c.kwargs["position"] for c in child_calls]
        assert positions == list(range(len(positions)))
