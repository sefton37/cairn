"""Round-trip integration tests for RPC methods that are ONLY available on the
stdio transport (not exposed via HTTP /rpc/dev).

Exercises the full JSON-RPC 2.0 dispatch path through _handle_jsonrpc_request
for each method group. No LLM calls. External I/O (Thunderbird, Ollama) is
mocked only where the handler requires it.
"""
from __future__ import annotations

import json
import struct
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def rpc_db(tmp_path, monkeypatch, isolated_db_singleton):
    """Isolated DB for round-trip RPC tests.

    Resets both the cairn.db singleton (via isolated_db_singleton) and the
    play_db thread-local connection.  Also resets every module-level _service
    singleton that touches play_db so each test starts from a clean state.
    """
    monkeypatch.setenv("TALKINGROCK_DATA_DIR", str(tmp_path / "data"))

    import cairn.play_db as play_db
    import cairn.rpc_handlers.memories as mem_handlers
    import cairn.rpc_handlers.briefing as briefing_handlers

    play_db.close_connection()
    play_db.init_db()

    # Reset service singletons so they pick up the new play_db connection.
    mem_handlers._service = None
    briefing_handlers._service = None

    from cairn.db import get_db
    from cairn import play_db as _play_db

    _play_db.close_connection()
    db = get_db()
    yield db

    play_db.close_connection()
    mem_handlers._service = None
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
# Memory Service factory helpers (mocked deps — no Ollama, no sentence
# transformers needed)
# =============================================================================


def _make_embedding(value: float = 0.5) -> bytes:
    """Create a fake 384-dim embedding (matches real sentence-transformers output size)."""
    return struct.pack("f" * 384, *([value] * 384))


def _mock_provider() -> MagicMock:
    provider = MagicMock()
    provider.chat_json.return_value = json.dumps(
        {"is_match": False, "reason": "test", "merged_narrative": ""}
    )
    return provider


def _mock_embedding_service() -> MagicMock:
    svc = MagicMock()
    svc.embed.return_value = _make_embedding()
    svc.find_similar.return_value = []
    svc.is_available = True
    return svc


def _make_service():
    from cairn.services.memory_service import MemoryService

    return MemoryService(
        provider=_mock_provider(),
        embedding_service=_mock_embedding_service(),
        graph_store=MagicMock(),
    )


def _make_conversation(rpc_db) -> str:
    """Create a conversation with one message and return its ID."""
    from cairn.services.conversation_service import ConversationService

    svc = ConversationService()
    conv = svc.start()
    svc.add_message(conv.id, "user", "Test message for memory tests.")
    return conv.id


# =============================================================================
# Memory Lifecycle Tests
# =============================================================================


class TestMemoriesLifecycle:
    """Round-trip tests for lifecycle/memories/* methods."""

    def test_memories_pending_empty_on_fresh_db(self, rpc_db) -> None:
        """lifecycle/memories/pending returns an empty list on a fresh database."""
        resp = _rpc(rpc_db, req_id=1, method="lifecycle/memories/pending")

        assert "result" in resp
        assert resp["result"]["memories"] == []

    def test_memories_list_empty_on_fresh_db(self, rpc_db) -> None:
        """lifecycle/memories/list returns an empty list on a fresh database."""
        resp = _rpc(rpc_db, req_id=2, method="lifecycle/memories/list")

        assert "result" in resp
        assert resp["result"]["memories"] == []

    def test_memories_get_not_found(self, rpc_db) -> None:
        """lifecycle/memories/get with a nonexistent ID returns memory: null."""
        resp = _rpc(
            rpc_db,
            req_id=3,
            method="lifecycle/memories/get",
            params={"memory_id": "does-not-exist"},
        )

        assert "result" in resp
        assert resp["result"]["memory"] is None

    def test_memories_approve_reject_cycle(self, rpc_db) -> None:
        """Create a memory, approve it, verify status is approved; create another,
        reject it, verify status is rejected."""
        conv_id = _make_conversation(rpc_db)
        svc = _make_service()
        mem = svc.store(conv_id, "We chose SQLite for local-first storage.")

        # Approve
        approve_resp = _rpc(
            rpc_db,
            req_id=4,
            method="lifecycle/memories/approve",
            params={"memory_id": mem.id},
        )
        assert "result" in approve_resp
        assert approve_resp["result"]["memory"]["status"] == "approved"

        # Reject a second memory
        mem2 = svc.store(conv_id, "Temporary decision that was overruled.")
        reject_resp = _rpc(
            rpc_db,
            req_id=5,
            method="lifecycle/memories/reject",
            params={"memory_id": mem2.id},
        )
        assert "result" in reject_resp
        assert reject_resp["result"]["memory"]["status"] == "rejected"

    def test_memories_edit_updates_narrative(self, rpc_db) -> None:
        """lifecycle/memories/edit changes the narrative and the change is
        visible via lifecycle/memories/get."""
        conv_id = _make_conversation(rpc_db)
        svc = _make_service()
        mem = svc.store(conv_id, "Original narrative text.")

        edit_resp = _rpc(
            rpc_db,
            req_id=6,
            method="lifecycle/memories/edit",
            params={"memory_id": mem.id, "narrative": "Corrected narrative text."},
        )
        assert "result" in edit_resp
        assert edit_resp["result"]["memory"]["narrative"] == "Corrected narrative text."

        get_resp = _rpc(
            rpc_db,
            req_id=7,
            method="lifecycle/memories/get",
            params={"memory_id": mem.id},
        )
        assert get_resp["result"]["memory"]["narrative"] == "Corrected narrative text."

    def test_memories_delete_removes_memory(self, rpc_db) -> None:
        """lifecycle/memories/delete removes the memory; subsequent get returns null."""
        conv_id = _make_conversation(rpc_db)
        svc = _make_service()
        mem = svc.store(conv_id, "Memory that will be deleted.")

        del_resp = _rpc(
            rpc_db,
            req_id=8,
            method="lifecycle/memories/delete",
            params={"memory_id": mem.id},
        )
        assert "result" in del_resp
        assert del_resp["result"]["deleted"] is True

        get_resp = _rpc(
            rpc_db,
            req_id=9,
            method="lifecycle/memories/get",
            params={"memory_id": mem.id},
        )
        assert get_resp["result"]["memory"] is None

    def test_memories_search_fts(self, rpc_db) -> None:
        """lifecycle/memories/search_fts finds a memory whose narrative contains
        the search token."""
        conv_id = _make_conversation(rpc_db)
        svc = _make_service()
        svc.store(conv_id, "The team adopted asyncpg for database access.")

        resp = _rpc(
            rpc_db,
            req_id=10,
            method="lifecycle/memories/search_fts",
            params={"query": "asyncpg"},
        )

        assert "result" in resp
        assert resp["result"]["query"] == "asyncpg"
        result_ids = [r["id"] for r in resp["result"]["results"]]
        assert len(result_ids) >= 1

    def test_memories_by_conversation(self, rpc_db) -> None:
        """lifecycle/memories/by_conversation returns memories linked to a
        specific conversation."""
        conv_id = _make_conversation(rpc_db)
        svc = _make_service()
        mem = svc.store(conv_id, "Decision made in this conversation.")

        resp = _rpc(
            rpc_db,
            req_id=11,
            method="lifecycle/memories/by_conversation",
            params={"conversation_id": conv_id},
        )

        assert "result" in resp
        ids = [m["id"] for m in resp["result"]["memories"]]
        assert mem.id in ids

    def test_memories_entity_type_counts(self, rpc_db) -> None:
        """lifecycle/memories/entity_type_counts returns a counts dict and a
        status field even when the approved bucket is empty."""
        resp = _rpc(rpc_db, req_id=12, method="lifecycle/memories/entity_type_counts")

        assert "result" in resp
        result = resp["result"]
        assert "counts" in result
        assert "status" in result
        assert result["status"] == "approved"

    def test_memories_open_threads(self, rpc_db) -> None:
        """lifecycle/memories/open_threads returns a threads list (empty on
        fresh DB)."""
        resp = _rpc(rpc_db, req_id=13, method="lifecycle/memories/open_threads")

        assert "result" in resp
        assert "threads" in resp["result"]
        assert isinstance(resp["result"]["threads"], list)

    def test_memories_ensure_page(self, rpc_db) -> None:
        """lifecycle/memories/ensure_page creates a Memories page for an act
        and returns a non-empty page_id."""
        from cairn.play_db import create_act

        _, act_id = create_act(title="Test Act for Ensure Page")

        resp = _rpc(
            rpc_db,
            req_id=14,
            method="lifecycle/memories/ensure_page",
            params={"act_id": act_id},
        )

        assert "result" in resp
        assert "page_id" in resp["result"]
        assert isinstance(resp["result"]["page_id"], str)
        assert resp["result"]["page_id"]  # non-empty

    def test_memories_ensure_page_is_idempotent(self, rpc_db) -> None:
        """lifecycle/memories/ensure_page called twice returns the same page_id."""
        from cairn.play_db import create_act

        _, act_id = create_act(title="Idempotent Act")

        resp1 = _rpc(
            rpc_db,
            req_id=15,
            method="lifecycle/memories/ensure_page",
            params={"act_id": act_id},
        )
        resp2 = _rpc(
            rpc_db,
            req_id=16,
            method="lifecycle/memories/ensure_page",
            params={"act_id": act_id},
        )

        assert resp1["result"]["page_id"] == resp2["result"]["page_id"]


# =============================================================================
# Briefing Tests
# =============================================================================


class TestBriefing:
    """Round-trip tests for lifecycle/briefing/* methods."""

    def test_briefing_get_returns_none_fresh_db(self, rpc_db) -> None:
        """lifecycle/briefing/get returns null when no briefing has been
        generated yet."""
        resp = _rpc(rpc_db, req_id=20, method="lifecycle/briefing/get")

        assert "result" in resp
        assert resp["result"]["briefing"] is None

    def test_briefing_generate_mocked(self, rpc_db) -> None:
        """lifecycle/briefing/generate dispatches through the service and returns
        a briefing dict when StateBriefingService is mocked."""
        fake_briefing = {
            "id": "brief-1",
            "summary": "All systems nominal.",
            "created_at": "2026-01-01T00:00:00Z",
        }

        mock_briefing = MagicMock()
        mock_briefing.to_dict.return_value = fake_briefing

        mock_svc = MagicMock()
        mock_svc.generate.return_value = mock_briefing

        with patch("cairn.rpc_handlers.briefing._get_service", return_value=mock_svc):
            resp = _rpc(rpc_db, req_id=21, method="lifecycle/briefing/generate")

        assert "result" in resp
        assert resp["result"]["briefing"] == fake_briefing

    def test_briefing_generate_with_trigger(self, rpc_db) -> None:
        """lifecycle/briefing/generate forwards the trigger param to the service."""
        mock_briefing = MagicMock()
        mock_briefing.to_dict.return_value = {"summary": "test"}

        mock_svc = MagicMock()
        mock_svc.generate.return_value = mock_briefing

        with patch("cairn.rpc_handlers.briefing._get_service", return_value=mock_svc):
            _rpc(
                rpc_db,
                req_id=22,
                method="lifecycle/briefing/generate",
                params={"trigger": "wake"},
            )

        mock_svc.generate.assert_called_once_with(trigger="wake")


# =============================================================================
# Email Operations Tests
# =============================================================================


def _mock_store_with_conn(conn: MagicMock) -> MagicMock:
    """Return a mock CairnStore whose _get_connection() returns the given conn."""
    store = MagicMock()
    store._get_connection.return_value = conn
    return store


class TestEmailOperations:
    """Round-trip tests for cairn/email/* methods."""

    def test_email_open_not_found(self, rpc_db) -> None:
        """cairn/email/open with a message_id absent from email_cache returns
        an RpcError response (error key in envelope)."""
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = None
        store = _mock_store_with_conn(conn)

        with patch("cairn.cairn.store.get_cairn_store", return_value=store):
            resp = _rpc(
                rpc_db,
                req_id=30,
                method="cairn/email/open",
                params={"email_message_id": 999},
            )

        assert "error" in resp
        assert resp["error"]["code"] == -32001

    def test_email_dismiss_not_found(self, rpc_db) -> None:
        """cairn/email/dismiss with a bad message_id returns RpcError -32001."""
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = None
        store = _mock_store_with_conn(conn)

        with patch("cairn.cairn.store.get_cairn_store", return_value=store):
            resp = _rpc(
                rpc_db,
                req_id=31,
                method="cairn/email/dismiss",
                params={"email_message_id": 999},
            )

        assert "error" in resp
        assert resp["error"]["code"] == -32001

    def test_email_snooze_dispatches_correctly(self, rpc_db) -> None:
        """cairn/email/snooze forwards message_id and hours to the store and
        returns success: True."""
        row = MagicMock()
        row.__getitem__ = lambda self, k: 42 if k == "gloda_message_id" else None
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = row

        store = _mock_store_with_conn(conn)

        with patch("cairn.cairn.store.get_cairn_store", return_value=store):
            resp = _rpc(
                rpc_db,
                req_id=32,
                method="cairn/email/snooze",
                params={"email_message_id": 42, "hours": 8},
            )

        assert "result" in resp
        assert resp["result"]["success"] is True
        assert resp["result"]["message_id"] == 42

    def test_email_upvote_dispatches_correctly(self, rpc_db) -> None:
        """cairn/email/upvote forwards message_id and returns success: True."""
        row = MagicMock()
        row.__getitem__ = lambda self, k: {
            "gloda_message_id": 7,
            "sender_email": "alice@example.com",
            "importance_score": 0.5,
        }.get(k)
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = row

        store = _mock_store_with_conn(conn)

        with patch("cairn.cairn.store.get_cairn_store", return_value=store):
            resp = _rpc(
                rpc_db,
                req_id=33,
                method="cairn/email/upvote",
                params={"email_message_id": 7},
            )

        assert "result" in resp
        assert resp["result"]["success"] is True

    def test_email_downvote_dispatches_correctly(self, rpc_db) -> None:
        """cairn/email/downvote forwards message_id and returns success: True."""
        row = MagicMock()
        row.__getitem__ = lambda self, k: {
            "gloda_message_id": 8,
            "sender_email": "bob@example.com",
            "importance_score": 0.5,
        }.get(k)
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = row

        store = _mock_store_with_conn(conn)

        with patch("cairn.cairn.store.get_cairn_store", return_value=store):
            resp = _rpc(
                rpc_db,
                req_id=34,
                method="cairn/email/downvote",
                params={"email_message_id": 8},
            )

        assert "result" in resp
        assert resp["result"]["success"] is True


# =============================================================================
# Consciousness Persist Tests
# =============================================================================


class TestConsciousnessPersist:
    """Round-trip tests for consciousness/persist."""

    def _make_fake_observer(self, events: list | None = None) -> MagicMock:
        observer = MagicMock()
        observer.get_all.return_value = events or []
        return observer

    def test_consciousness_persist_creates_block_hierarchy(self, rpc_db) -> None:
        """consciousness/persist with valid params creates blocks and returns
        chain_block_id."""
        from cairn.services.conversation_service import ConversationService

        svc = ConversationService()
        conv = svc.start()
        user_msg = svc.add_message(conv.id, "user", "Hello.")
        bot_msg = svc.add_message(conv.id, "cairn", "Hi there.")

        from cairn.play_db import create_act
        _, act_id = create_act(title="Consciousness Test Act")

        fake_observer = self._make_fake_observer()

        with patch(
            "cairn.cairn.consciousness_stream.ConsciousnessObserver.get_instance",
            return_value=fake_observer,
        ):
            resp = _rpc(
                rpc_db,
                req_id=40,
                method="consciousness/persist",
                params={
                    "conversation_id": conv.id,
                    "user_message_id": user_msg.id,
                    "response_message_id": bot_msg.id,
                    "act_id": act_id,
                },
            )

        assert "result" in resp
        assert resp["result"]["chain_block_id"] is not None
        assert isinstance(resp["result"]["event_count"], int)

    def test_consciousness_persist_no_act_returns_error(self, rpc_db) -> None:
        """consciousness/persist with no act_id and no active act returns an
        error payload (not an RpcError envelope)."""
        from cairn.services.conversation_service import ConversationService

        svc = ConversationService()
        conv = svc.start()
        user_msg = svc.add_message(conv.id, "user", "Hello.")
        bot_msg = svc.add_message(conv.id, "cairn", "Hi.")

        fake_observer = self._make_fake_observer()

        # Ensure list_acts returns no active act
        with patch(
            "cairn.cairn.consciousness_stream.ConsciousnessObserver.get_instance",
            return_value=fake_observer,
        ), patch(
            "cairn.play_db.list_acts",
            return_value=([], None),
        ):
            resp = _rpc(
                rpc_db,
                req_id=41,
                method="consciousness/persist",
                params={
                    "conversation_id": conv.id,
                    "user_message_id": user_msg.id,
                    "response_message_id": bot_msg.id,
                },
            )

        # The handler returns a result dict with an "error" key (not a JSON-RPC error)
        assert "result" in resp
        assert "error" in resp["result"]
        assert resp["result"]["chain_block_id"] is None

    def test_consciousness_persist_with_explicit_act_id(self, rpc_db) -> None:
        """consciousness/persist with an explicit act_id uses that act and
        does not call list_acts."""
        from cairn.services.conversation_service import ConversationService
        from cairn.play_db import create_act

        svc = ConversationService()
        conv = svc.start()
        user_msg = svc.add_message(conv.id, "user", "Explicit act test.")
        bot_msg = svc.add_message(conv.id, "cairn", "Acknowledged.")

        _, act_id = create_act(title="Explicit Act")

        fake_observer = self._make_fake_observer()

        with patch(
            "cairn.cairn.consciousness_stream.ConsciousnessObserver.get_instance",
            return_value=fake_observer,
        ), patch(
            "cairn.play_db.list_acts"
        ) as mock_list_acts:
            resp = _rpc(
                rpc_db,
                req_id=42,
                method="consciousness/persist",
                params={
                    "conversation_id": conv.id,
                    "user_message_id": user_msg.id,
                    "response_message_id": bot_msg.id,
                    "act_id": act_id,
                },
            )

        assert "result" in resp
        assert resp["result"]["chain_block_id"] is not None
        # list_acts should NOT have been called since act_id was explicit
        mock_list_acts.assert_not_called()


# =============================================================================
# Attention Rules Tests
# =============================================================================


class TestAttentionRules:
    """Round-trip tests for cairn/attention/rules/* methods."""

    def test_attention_rules_list_empty(self, rpc_db) -> None:
        """cairn/attention/rules/list returns an empty rules list on a fresh DB."""
        resp = _rpc(rpc_db, req_id=50, method="cairn/attention/rules/list")

        assert "result" in resp
        assert resp["result"]["rules"] == []

    def test_attention_rules_create_and_list(self, rpc_db) -> None:
        """Creating a rule via cairn/attention/rules/create makes it appear in
        cairn/attention/rules/list."""
        create_resp = _rpc(
            rpc_db,
            req_id=51,
            method="cairn/attention/rules/create",
            params={
                "feature_type": "sender_email",
                "feature_value": "boss@example.com",
                "boost_score": 0.9,
                "confidence": 1.0,
                "sample_count": 1,
                "description": "Emails from boss are high-priority",
                "active": 1,
            },
        )

        assert "result" in create_resp
        created_rule = create_resp["result"]["rule"]
        assert created_rule["feature_type"] == "sender_email"
        assert created_rule["feature_value"] == "boss@example.com"

        list_resp = _rpc(rpc_db, req_id=52, method="cairn/attention/rules/list")
        rule_ids = [r["id"] for r in list_resp["result"]["rules"]]
        assert created_rule["id"] in rule_ids

    def test_attention_rules_update(self, rpc_db) -> None:
        """cairn/attention/rules/update modifies an existing rule's fields."""
        create_resp = _rpc(
            rpc_db,
            req_id=53,
            method="cairn/attention/rules/create",
            params={
                "feature_type": "sender_email",
                "feature_value": "newsletter@example.com",
                "boost_score": 0.3,
                "confidence": 0.8,
                "sample_count": 2,
                "description": "Newsletter sender",
                "active": 1,
            },
        )
        rule_id = create_resp["result"]["rule"]["id"]

        update_resp = _rpc(
            rpc_db,
            req_id=54,
            method="cairn/attention/rules/update",
            params={"id": rule_id, "boost_score": 0.6, "description": "Updated desc"},
        )

        assert "result" in update_resp
        assert update_resp["result"]["ok"] is True

        # Verify via list_all that the change persisted
        list_all_resp = _rpc(
            rpc_db, req_id=55, method="cairn/attention/rules/list_all"
        )
        updated = next(
            r for r in list_all_resp["result"]["rules"] if r["id"] == rule_id
        )
        assert updated["boost_score"] == 0.6
        assert updated["description"] == "Updated desc"

    def test_attention_rules_delete(self, rpc_db) -> None:
        """cairn/attention/rules/delete removes a rule so it no longer appears
        in list."""
        create_resp = _rpc(
            rpc_db,
            req_id=56,
            method="cairn/attention/rules/create",
            params={
                "feature_type": "sender_email",
                "feature_value": "spam@example.com",
                "boost_score": -0.5,
                "confidence": 1.0,
                "sample_count": 5,
                "description": "Known spam",
                "active": 1,
            },
        )
        rule_id = create_resp["result"]["rule"]["id"]

        del_resp = _rpc(
            rpc_db,
            req_id=57,
            method="cairn/attention/rules/delete",
            params={"id": rule_id},
        )
        assert "result" in del_resp

        list_resp = _rpc(rpc_db, req_id=58, method="cairn/attention/rules/list")
        rule_ids = [r["id"] for r in list_resp["result"]["rules"]]
        assert rule_id not in rule_ids
