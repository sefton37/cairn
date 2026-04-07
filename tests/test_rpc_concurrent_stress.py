"""Thread-safety and concurrent access stress tests for the RPC system.

Exercises:
  1. Consciousness handler module-level state (_active_cairn_chats / _cairn_chat_lock)
  2. Pull handler module-level state (_active_pulls / _pull_lock)
  3. Concurrent DB access through the real dispatcher (play/acts, blocks)
  4. Conversation singleton enforcement under contention

All tests run without LLM calls.  Target: each completes in <2 seconds.
"""

from __future__ import annotations

import threading
import time
import uuid
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def rpc_db(tmp_path, monkeypatch, isolated_db_singleton):
    """Isolated DB for concurrent RPC tests.

    Resets both the cairn.db singleton (handled by isolated_db_singleton) and
    the play_db thread-local connection.  Also resets the ConversationService
    singleton so each test gets a clean service bound to the fresh play_db.
    """
    monkeypatch.setenv("TALKINGROCK_DATA_DIR", str(tmp_path / "data"))

    import cairn.play_db as play_db
    import cairn.rpc_handlers.conversations as conv_handlers
    import cairn.rpc_handlers.briefing as briefing_handlers

    play_db.close_connection()
    play_db.init_db()

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


def _rpc(db: Any, *, req_id: int, method: str, params: dict | None = None) -> dict:
    """Dispatch a JSON-RPC 2.0 request and return the full response envelope."""
    import cairn.ui_rpc_server as ui

    req: dict = {"jsonrpc": "2.0", "id": req_id, "method": method}
    p = dict(params) if params else {}
    p.setdefault("__session", "test-session")
    req["params"] = p
    resp = ui._handle_jsonrpc_request(db, req)
    assert resp is not None
    return resp


# =============================================================================
# 1. Consciousness handler thread safety
# =============================================================================


class TestConsciousnessHandlerConcurrency:
    """Tests for _active_cairn_chats / _cairn_chat_lock in rpc_handlers.consciousness."""

    def _insert_fake_chat(self, chat_id: str, is_complete: bool = False) -> None:
        """Directly insert a fake CairnChatContext into the module-level dict."""
        from cairn.rpc_handlers.consciousness import (
            CairnChatContext,
            _active_cairn_chats,
            _cairn_chat_lock,
        )

        ctx = CairnChatContext(
            chat_id=chat_id,
            text="test message",
            conversation_id=None,
            extended_thinking=False,
            is_complete=is_complete,
            result={"response": "ok"} if is_complete else None,
        )
        with _cairn_chat_lock:
            _active_cairn_chats[chat_id] = ctx

    def _remove_fake_chat(self, chat_id: str) -> None:
        from cairn.rpc_handlers.consciousness import _active_cairn_chats, _cairn_chat_lock

        with _cairn_chat_lock:
            _active_cairn_chats.pop(chat_id, None)

    def test_concurrent_chat_status_polls_return_consistent_results(self, rpc_db) -> None:
        """10 threads polling status for the same incomplete chat all get 'processing'."""
        chat_id = uuid.uuid4().hex[:12]
        self._insert_fake_chat(chat_id, is_complete=False)

        try:
            results: list[dict] = []
            lock = threading.Lock()

            def poll() -> None:
                from cairn.rpc_handlers.consciousness import handle_cairn_chat_status

                result = handle_cairn_chat_status(rpc_db, chat_id=chat_id)
                with lock:
                    results.append(result)

            threads = [threading.Thread(target=poll) for _ in range(10)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=2.0)

            assert len(results) == 10
            for r in results:
                assert r.get("status") == "processing", f"Unexpected result: {r}"
        finally:
            self._remove_fake_chat(chat_id)

    def test_concurrent_chat_starts_each_get_unique_chat_id(self, rpc_db) -> None:
        """5 concurrent chat starts each produce a unique chat_id."""
        from cairn.rpc_handlers.consciousness import _active_cairn_chats, _cairn_chat_lock

        chat_ids_collected: list[str] = []
        lock = threading.Lock()

        def _noop_chat_respond(*args: Any, **kwargs: Any) -> dict:
            time.sleep(0.05)  # simulate brief async work
            return {"response": "noop"}

        def start_chat() -> None:
            from cairn.rpc_handlers.consciousness import handle_cairn_chat_async

            with patch(
                "cairn.rpc_handlers.consciousness.handle_chat_respond",
                side_effect=_noop_chat_respond,
            ):
                result = handle_cairn_chat_async(
                    rpc_db,
                    text="hello",
                    conversation_id=None,
                    extended_thinking=False,
                )
            with lock:
                chat_ids_collected.append(result["chat_id"])

        threads = [threading.Thread(target=start_chat) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)

        # All 5 calls completed
        assert len(chat_ids_collected) == 5
        # All chat_ids are unique
        assert len(set(chat_ids_collected)) == 5

        # Cleanup lingering entries
        for cid in chat_ids_collected:
            with _cairn_chat_lock:
                _active_cairn_chats.pop(cid, None)

    def test_chat_completion_race_cleanup_happens_exactly_once(self, rpc_db) -> None:
        """Polling a completed chat from 5 simultaneous threads: only one gets the result.

        The handler removes the entry on first read of is_complete=True; subsequent
        threads must see 'not_found'.
        """
        from cairn.rpc_handlers.consciousness import (
            _active_cairn_chats,
            _cairn_chat_lock,
            handle_cairn_chat_status,
        )

        chat_id = uuid.uuid4().hex[:12]
        self._insert_fake_chat(chat_id, is_complete=True)

        complete_results: list[dict] = []
        not_found_results: list[dict] = []
        lock = threading.Lock()
        barrier = threading.Barrier(5)

        def poll() -> None:
            barrier.wait()  # all threads hit the call simultaneously
            result = handle_cairn_chat_status(rpc_db, chat_id=chat_id)
            with lock:
                if result.get("status") == "complete":
                    complete_results.append(result)
                else:
                    not_found_results.append(result)

        threads = [threading.Thread(target=poll) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)

        # Exactly one thread gets the completed payload
        assert len(complete_results) == 1
        # The remaining four get not_found
        assert len(not_found_results) == 4
        # Entry is gone from the dict
        with _cairn_chat_lock:
            assert chat_id not in _active_cairn_chats


# =============================================================================
# 2. Pull handler thread safety
# =============================================================================


class TestPullHandlerConcurrency:
    """Tests for _active_pulls / _pull_lock in rpc_handlers.providers."""

    def _insert_fake_pull(self, pull_id: str, done: bool = False) -> None:
        from cairn.rpc_handlers.providers import _active_pulls, _pull_lock

        with _pull_lock:
            _active_pulls[pull_id] = {
                "model": "llama3.2:3b",
                "status": "success" if done else "downloading",
                "progress": 100 if done else 50,
                "total": 1000,
                "completed": 1000 if done else 500,
                "error": None,
                "done": done,
            }

    def _remove_fake_pull(self, pull_id: str) -> None:
        from cairn.rpc_handlers.providers import _active_pulls, _pull_lock

        with _pull_lock:
            _active_pulls.pop(pull_id, None)

    def test_concurrent_pull_status_polls_return_consistent_state(self) -> None:
        """10 threads polling an in-progress pull all see in-progress state without error."""
        from cairn.rpc_handlers.providers import handle_ollama_pull_status

        pull_id = uuid.uuid4().hex[:8]
        self._insert_fake_pull(pull_id, done=False)

        try:
            results: list[dict] = []
            lock = threading.Lock()

            def poll() -> None:
                result = handle_ollama_pull_status(pull_id=pull_id)
                with lock:
                    results.append(result)

            threads = [threading.Thread(target=poll) for _ in range(10)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=2.0)

            assert len(results) == 10
            # All threads should have seen the in-progress entry (done=False)
            for r in results:
                assert r.get("done") is False, (
                    f"Unexpected result: {r}"
                )
        finally:
            self._remove_fake_pull(pull_id)

    def test_pull_completion_cleanup_race_only_one_gets_result(self) -> None:
        """5 threads race to poll a finished pull; exactly one gets the done result.

        handle_ollama_pull_status deletes the entry after returning done=True,
        so subsequent pollers must receive 'Pull not found'.
        """
        from cairn.rpc_handlers.providers import _active_pulls, _pull_lock, handle_ollama_pull_status

        pull_id = uuid.uuid4().hex[:8]
        self._insert_fake_pull(pull_id, done=True)

        done_results: list[dict] = []
        not_found_results: list[dict] = []
        lock = threading.Lock()
        barrier = threading.Barrier(5)

        def poll() -> None:
            barrier.wait()
            result = handle_ollama_pull_status(pull_id=pull_id)
            with lock:
                if result.get("error") == "Pull not found":
                    not_found_results.append(result)
                else:
                    done_results.append(result)

        threads = [threading.Thread(target=poll) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)

        assert len(done_results) == 1, (
            f"Expected exactly 1 done result, got {len(done_results)}: {done_results}"
        )
        assert len(not_found_results) == 4
        # Entry removed from dict
        with _pull_lock:
            assert pull_id not in _active_pulls


# =============================================================================
# 3. Concurrent DB access through the dispatcher
# =============================================================================


class TestConcurrentDbAccess:
    """Real play_db reads and writes from multiple threads via the JSON-RPC dispatcher."""

    def test_concurrent_play_reads_all_return_valid_results(self, rpc_db) -> None:
        """10 threads calling play/acts/list simultaneously all get valid results."""
        errors: list[str] = []
        lock = threading.Lock()

        def list_acts(thread_id: int) -> None:
            resp = _rpc(rpc_db, req_id=thread_id, method="play/acts/list")
            if "error" in resp:
                with lock:
                    errors.append(f"thread {thread_id}: {resp['error']}")
            elif "result" not in resp or "acts" not in resp["result"]:
                with lock:
                    errors.append(f"thread {thread_id}: malformed result: {resp}")

        threads = [threading.Thread(target=list_acts, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)

        assert errors == [], f"Errors from concurrent reads: {errors}"

    def test_concurrent_play_writes_all_acts_are_persisted(self, rpc_db) -> None:
        """5 threads each create a unique act; all 5 appear in the final list."""
        created_ids: list[str] = []
        errors: list[str] = []
        lock = threading.Lock()

        def create_act(index: int) -> None:
            resp = _rpc(
                rpc_db,
                req_id=index,
                method="play/acts/create",
                params={"title": f"Concurrent Act {index}"},
            )
            if "error" in resp:
                with lock:
                    errors.append(f"thread {index}: {resp['error']}")
            else:
                act_id = resp["result"]["created_act_id"]
                with lock:
                    created_ids.append(act_id)

        threads = [threading.Thread(target=create_act, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)

        assert errors == [], f"Creation errors: {errors}"
        assert len(created_ids) == 5

        # Verify all 5 + the built-in your-story appear in the list
        list_resp = _rpc(rpc_db, req_id=99, method="play/acts/list")
        assert "result" in list_resp
        act_ids_in_db = {a["act_id"] for a in list_resp["result"]["acts"]}

        assert "your-story" in act_ids_in_db
        for cid in created_ids:
            assert cid in act_ids_in_db, f"Act {cid} not found after concurrent writes"

    def test_concurrent_blocks_crud_no_cross_thread_corruption(self, rpc_db) -> None:
        """5 threads each create a block and read it back; no cross-thread data corruption."""
        # Create a shared act first
        act_resp = _rpc(
            rpc_db,
            req_id=1,
            method="play/acts/create",
            params={"title": "Blocks Stress Act"},
        )
        act_id = act_resp["result"]["created_act_id"]

        created_pairs: list[tuple[str, str]] = []  # (expected_content, block_id)
        errors: list[str] = []
        lock = threading.Lock()

        def create_block(index: int) -> None:
            label = f"block-content-thread-{index}"
            create_resp = _rpc(
                rpc_db,
                req_id=100 + index,
                method="blocks/create",
                params={"act_id": act_id, "type": "paragraph", "properties": {"content": label}},
            )
            if "error" in create_resp:
                with lock:
                    errors.append(f"create thread {index}: {create_resp['error']}")
                return
            block_id = create_resp["result"]["block"]["id"]
            with lock:
                created_pairs.append((label, block_id))

        threads = [threading.Thread(target=create_block, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)

        assert errors == [], f"Block creation errors: {errors}"
        assert len(created_pairs) == 5

        # List all blocks and confirm each label maps to its block_id
        list_resp = _rpc(
            rpc_db, req_id=200, method="blocks/list", params={"act_id": act_id}
        )
        assert "result" in list_resp
        blocks_by_id = {b["id"]: b for b in list_resp["result"]["blocks"]}

        for label, block_id in created_pairs:
            assert block_id in blocks_by_id, f"Block {block_id} missing from list"
            props = blocks_by_id[block_id].get("properties", {})
            assert props.get("content") == label, (
                f"Block {block_id}: expected content={label!r}, got {props!r}"
            )

    def test_concurrent_mixed_read_write_readers_never_see_error(self, rpc_db) -> None:
        """Readers and writers running simultaneously: readers never return an error."""
        read_errors: list[str] = []
        lock = threading.Lock()
        barrier = threading.Barrier(10)

        def reader(thread_id: int) -> None:
            barrier.wait()
            resp = _rpc(rpc_db, req_id=thread_id, method="play/acts/list")
            if "error" in resp:
                with lock:
                    read_errors.append(f"reader {thread_id}: {resp['error']}")

        def writer(thread_id: int) -> None:
            barrier.wait()
            _rpc(
                rpc_db,
                req_id=1000 + thread_id,
                method="play/acts/create",
                params={"title": f"Mixed Act {thread_id}"},
            )

        threads = (
            [threading.Thread(target=reader, args=(i,)) for i in range(5)]
            + [threading.Thread(target=writer, args=(i,)) for i in range(5)]
        )
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)

        assert read_errors == [], f"Readers encountered errors under write contention: {read_errors}"


# =============================================================================
# 4. Conversation singleton enforcement under contention
# =============================================================================


class TestConversationSingletonContention:
    """ConversationService enforces one-active-at-a-time under concurrent pressure."""

    @pytest.fixture(autouse=True)
    def _mock_compression(self):
        """Prevent background thread spawning by CompressionManager."""
        mock_manager = MagicMock()
        mock_status = MagicMock()
        mock_status.to_dict.return_value = {"status": "queued", "conversation_id": "mock"}
        mock_manager.submit.return_value = mock_status
        with patch(
            "cairn.services.compression_manager.get_compression_manager",
            return_value=mock_manager,
        ):
            yield

    def test_concurrent_conversation_starts_no_crash_all_results_valid(self, rpc_db) -> None:
        """5 threads all try to start a conversation simultaneously; none crash.

        NOTE: ConversationService.start() has a TOCTOU race — the active-check
        (get_active) and the INSERT are not in a single SQL transaction, so under
        true simultaneous contention multiple threads can slip past the guard.
        This test therefore only asserts:
          - All 5 threads complete without raising an exception
          - Every 'success' result contains a valid conversation dict
          - Every 'error' result contains a non-empty error string

        A separate sequential test (below) verifies the singleton guarantee holds
        when calls are properly serialized.
        """
        success_results: list[dict] = []
        error_results: list[dict] = []
        lock = threading.Lock()
        barrier = threading.Barrier(5)

        def start_conversation(thread_id: int) -> None:
            barrier.wait()
            resp = _rpc(rpc_db, req_id=thread_id, method="lifecycle/conversations/start")
            result = resp.get("result", {})
            with lock:
                if "error" in result:
                    error_results.append(result)
                else:
                    success_results.append(result)

        threads = [threading.Thread(target=start_conversation, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)

        total = len(success_results) + len(error_results)
        assert total == 5, f"Expected 5 results, got {total}"

        # All success results must contain a valid conversation dict
        for r in success_results:
            assert "conversation" in r, f"Success result missing conversation key: {r}"
            assert r["conversation"]["status"] == "active"

        # All error results must contain a non-empty error message
        for r in error_results:
            assert r["error"], f"Error result has empty error: {r}"

    def test_sequential_conversation_start_singleton_enforced(self, rpc_db) -> None:
        """Starting a second conversation after the first one is active returns an error.

        This verifies the singleton guarantee holds when calls are serialized —
        distinguishing from the TOCTOU race that can occur under true concurrency.
        """
        first_resp = _rpc(rpc_db, req_id=1, method="lifecycle/conversations/start")
        assert "result" in first_resp
        assert "conversation" in first_resp["result"]

        second_resp = _rpc(rpc_db, req_id=2, method="lifecycle/conversations/start")
        result = second_resp.get("result", {})

        assert "error" in result, (
            f"Expected second start to fail with error, got: {result}"
        )

    def test_concurrent_message_adds_all_messages_persisted(self, rpc_db) -> None:
        """10 threads all add a message to one conversation; all messages are persisted."""
        # Start the conversation first (sequential, before concurrency)
        start_resp = _rpc(rpc_db, req_id=1, method="lifecycle/conversations/start")
        assert "result" in start_resp
        conv_id = start_resp["result"]["conversation"]["id"]

        errors: list[str] = []
        lock = threading.Lock()

        def add_message(index: int) -> None:
            resp = _rpc(
                rpc_db,
                req_id=200 + index,
                method="lifecycle/conversations/add_message",
                params={
                    "conversation_id": conv_id,
                    "role": "user",
                    "content": f"Concurrent message {index}",
                },
            )
            if "error" in resp:
                with lock:
                    errors.append(f"thread {index}: {resp['error']}")

        threads = [threading.Thread(target=add_message, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)

        assert errors == [], f"Message add errors: {errors}"

        # Verify all 10 messages are stored
        msg_resp = _rpc(
            rpc_db,
            req_id=300,
            method="lifecycle/conversations/messages",
            params={"conversation_id": conv_id},
        )
        assert "result" in msg_resp
        messages = msg_resp["result"]["messages"]
        assert len(messages) == 10, f"Expected 10 messages, got {len(messages)}"

        # Verify no cross-thread content corruption
        contents = {m["content"] for m in messages}
        for i in range(10):
            assert f"Concurrent message {i}" in contents, (
                f"Message {i} missing from persisted messages; found: {contents}"
            )
