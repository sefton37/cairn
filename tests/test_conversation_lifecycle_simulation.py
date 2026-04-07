"""End-to-end simulation tests for the conversation lifecycle state machine.

Tests the full state machine against a real DB, with only LLM calls mocked.
All assertions verify actual DB state, not just return values.

State machine:
    active ──close──> ready_to_close ──start_compression──> compressing ──archive──> archived
                           ↓                                     ↓
                        resume → active               fail_compression → ready_to_close
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def rpc_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_db_singleton):
    """Fresh play DB in a temp dir, with the global DB singleton isolated."""
    monkeypatch.setenv("TALKINGROCK_DATA_DIR", str(tmp_path / "data"))
    from cairn import play_db
    from cairn.db import get_db

    play_db.close_connection()
    db = get_db()
    yield db
    play_db.close_connection()


@pytest.fixture(autouse=True)
def reset_service_singleton():
    """Reset the ConversationService singleton between tests.

    The conversations RPC module caches a service instance in _service.
    Tests must start with a clean slate so each gets a fresh ConversationService
    (which calls init_db() on construction).
    """
    import cairn.rpc_handlers.conversations as conv_mod

    conv_mod._service = None
    yield
    conv_mod._service = None


@pytest.fixture(autouse=True)
def mock_compression_manager():
    """Replace the real CompressionManager with a no-op mock.

    The close RPC handler submits a job to the background CompressionManager.
    Tests that want to drive compression manually should use the pipeline directly.
    This fixture prevents spurious background threads and state mutations.
    """
    mock_mgr = MagicMock()
    mock_status = MagicMock()
    mock_status.to_dict.return_value = {
        "conversation_id": "test",
        "state": "queued",
        "error": None,
        "result_memory_ids": None,
    }
    mock_mgr.submit.return_value = mock_status
    mock_mgr.get_status.return_value = mock_status

    with patch(
        "cairn.rpc_handlers.conversations.get_compression_manager",
        return_value=mock_mgr,
    ):
        yield mock_mgr


# =============================================================================
# Helper
# =============================================================================


def _rpc(db, *, req_id: int, method: str, params: dict | None = None) -> dict:
    """Send a JSON-RPC 2.0 request through the dispatcher and return the response."""
    import cairn.ui_rpc_server as ui

    req: dict = {"jsonrpc": "2.0", "id": req_id, "method": method}
    p = dict(params) if params else {}
    p.setdefault("__session", "test-session")
    req["params"] = p
    resp = ui._handle_jsonrpc_request(db, req)
    assert resp is not None, f"Handler returned None for method={method}"
    return resp


def _result(resp: dict) -> dict:
    """Extract the result payload; fail if the response is an error."""
    assert "error" not in resp, f"RPC error: {resp['error']}"
    return resp["result"]


def _make_pipeline_mock(
    *,
    entities: dict | None = None,
    narrative: str = "User discussed project planning and next steps.",
    state_deltas: dict | None = None,
) -> MagicMock:
    """Return a mock OllamaProvider that feeds canned answers to the pipeline."""
    mock_provider = MagicMock()
    entities_json = json.dumps(entities or {})
    # chat_json is called for entity extraction and state delta detection
    mock_provider.chat_json.return_value = entities_json
    # chat_text is called for narrative compression
    mock_provider.chat_text.return_value = narrative
    mock_provider._model = "test-model"
    return mock_provider


# =============================================================================
# Group 1: State Machine Transitions (through RPC dispatcher)
# =============================================================================


class TestStateMachineTransitions:
    """Lifecycle transitions exercised through the full RPC dispatcher."""

    def test_start_creates_active_conversation(self, rpc_db):
        """start via RPC produces a conversation with status='active' in the DB."""
        from cairn import play_db

        resp = _rpc(rpc_db, req_id=1, method="lifecycle/conversations/start")
        result = _result(resp)

        assert "conversation" in result
        conv = result["conversation"]
        assert conv["status"] == "active"

        # Verify DB state
        conn = play_db._get_connection()
        row = conn.execute(
            "SELECT status FROM conversations WHERE id = ?", (conv["id"],)
        ).fetchone()
        assert row is not None
        assert row["status"] == "active"

    def test_singleton_constraint_via_rpc(self, rpc_db):
        """Starting a second conversation while one is active returns an error payload."""
        _rpc(rpc_db, req_id=1, method="lifecycle/conversations/start")

        resp = _rpc(rpc_db, req_id=2, method="lifecycle/conversations/start")
        result = resp["result"]

        # The handler returns a structured error (not an RPC protocol error)
        assert "error" in result
        assert "active_conversation" in result

    def test_add_messages_to_active_conversation(self, rpc_db):
        """Adding 3 messages via RPC is reflected in message_count and messages table."""
        from cairn import play_db

        start_resp = _rpc(rpc_db, req_id=1, method="lifecycle/conversations/start")
        conv_id = _result(start_resp)["conversation"]["id"]

        for i, (role, content) in enumerate(
            [("user", "Hello"), ("cairn", "Hi there"), ("user", "What's next?")],
            start=2,
        ):
            _rpc(
                rpc_db,
                req_id=i,
                method="lifecycle/conversations/add_message",
                params={"conversation_id": conv_id, "role": role, "content": content},
            )

        # Verify via messages RPC
        msg_resp = _rpc(
            rpc_db,
            req_id=5,
            method="lifecycle/conversations/messages",
            params={"conversation_id": conv_id},
        )
        messages = _result(msg_resp)["messages"]
        assert len(messages) == 3

        # Verify DB state
        conn = play_db._get_connection()
        count = conn.execute(
            "SELECT message_count FROM conversations WHERE id = ?", (conv_id,)
        ).fetchone()["message_count"]
        assert count == 3

    def test_close_transitions_to_ready_to_close(self, rpc_db):
        """close() via RPC transitions the conversation to ready_to_close in the DB."""
        from cairn import play_db

        start_resp = _rpc(rpc_db, req_id=1, method="lifecycle/conversations/start")
        conv_id = _result(start_resp)["conversation"]["id"]

        close_resp = _rpc(
            rpc_db,
            req_id=2,
            method="lifecycle/conversations/close",
            params={"conversation_id": conv_id},
        )
        conv = _result(close_resp)["conversation"]
        assert conv["status"] == "ready_to_close"

        # Verify DB state
        conn = play_db._get_connection()
        row = conn.execute(
            "SELECT status, closed_at FROM conversations WHERE id = ?", (conv_id,)
        ).fetchone()
        assert row["status"] == "ready_to_close"
        assert row["closed_at"] is not None

    def test_resume_transitions_back_to_active(self, rpc_db):
        """resume() via RPC brings a ready_to_close conversation back to active."""
        from cairn import play_db

        start_resp = _rpc(rpc_db, req_id=1, method="lifecycle/conversations/start")
        conv_id = _result(start_resp)["conversation"]["id"]

        _rpc(
            rpc_db,
            req_id=2,
            method="lifecycle/conversations/close",
            params={"conversation_id": conv_id},
        )

        resume_resp = _rpc(
            rpc_db,
            req_id=3,
            method="lifecycle/conversations/resume",
            params={"conversation_id": conv_id},
        )
        conv = _result(resume_resp)["conversation"]
        assert conv["status"] == "active"

        # Verify DB state
        conn = play_db._get_connection()
        row = conn.execute(
            "SELECT status FROM conversations WHERE id = ?", (conv_id,)
        ).fetchone()
        assert row["status"] == "active"

    def test_pause_and_unpause(self, rpc_db):
        """pause then unpause toggles is_paused in the DB without changing status."""
        from cairn import play_db

        start_resp = _rpc(rpc_db, req_id=1, method="lifecycle/conversations/start")
        conv_id = _result(start_resp)["conversation"]["id"]

        _rpc(
            rpc_db,
            req_id=2,
            method="lifecycle/conversations/pause",
            params={"conversation_id": conv_id},
        )

        conn = play_db._get_connection()
        paused_row = conn.execute(
            "SELECT is_paused FROM conversations WHERE id = ?", (conv_id,)
        ).fetchone()
        assert paused_row["is_paused"] == 1

        _rpc(
            rpc_db,
            req_id=3,
            method="lifecycle/conversations/unpause",
            params={"conversation_id": conv_id},
        )

        unpaused_row = conn.execute(
            "SELECT is_paused, status FROM conversations WHERE id = ?", (conv_id,)
        ).fetchone()
        assert unpaused_row["is_paused"] == 0
        assert unpaused_row["status"] == "active"


# =============================================================================
# Group 2: Compression Flow (mock LLM, real DB)
# =============================================================================


class TestCompressionFlow:
    """Compression pipeline exercised synchronously with a mocked LLM provider."""

    def _run_compression(self, rpc_db, conv_id: str, *, narrative: str) -> None:
        """Drive compression directly via ConversationService + CompressionPipeline."""
        from cairn.services.compression_manager import CompressionManager
        from cairn.services.compression_pipeline import (
            CompressionPipeline,
            format_transcript,
        )
        from cairn.services.conversation_service import ConversationService
        from cairn.services.memory_service import MemoryService

        service = ConversationService()
        messages = service.get_messages(conv_id)
        transcript = format_transcript(
            [{"role": m.role, "content": m.content} for m in messages]
        )

        mock_provider = _make_pipeline_mock(
            entities={"decisions": [{"what": "Use SQLite", "why": "Local-first"}]},
            narrative=narrative,
        )

        # Patch embedding service to avoid sentence-transformers dependency
        with patch(
            "cairn.services.compression_pipeline.CompressionPipeline.generate_embedding",
            return_value=None,
        ):
            with patch(
                "cairn.services.memory_service.get_embedding_service"
            ) as mock_emb_svc_factory:
                mock_emb_svc = MagicMock()
                mock_emb_svc.find_similar.return_value = []
                mock_emb_svc.embed.return_value = None
                mock_emb_svc_factory.return_value = mock_emb_svc

                pipeline = CompressionPipeline(provider=mock_provider)
                conv = service.get_by_id(conv_id)
                result = pipeline.compress(
                    transcript,
                    conversation_date=conv.started_at if conv else "2026-03-28",
                    message_count=len(messages),
                )

        # Store results using the manager's _store_results method
        memory_service = MemoryService()
        manager = CompressionManager(
            pipeline=pipeline, memory_service=memory_service
        )
        # Transition to compressing first
        service.start_compression(conv_id)

        with patch(
            "cairn.services.memory_service.get_embedding_service"
        ) as mock_emb_factory:
            mock_emb = MagicMock()
            mock_emb.find_similar.return_value = []
            mock_emb.embed.return_value = None
            mock_emb_factory.return_value = mock_emb
            manager._store_results(conv_id, result)

        service.archive(conv_id)

    def test_compression_produces_memories(self, rpc_db):
        """After synchronous compression, memories table has at least one row for the conversation."""
        from cairn import play_db

        start_resp = _rpc(rpc_db, req_id=1, method="lifecycle/conversations/start")
        conv_id = _result(start_resp)["conversation"]["id"]

        _rpc(
            rpc_db,
            req_id=2,
            method="lifecycle/conversations/add_message",
            params={
                "conversation_id": conv_id,
                "role": "user",
                "content": "We decided to use SQLite for local storage.",
            },
        )
        _rpc(
            rpc_db,
            req_id=3,
            method="lifecycle/conversations/close",
            params={"conversation_id": conv_id},
        )

        self._run_compression(
            rpc_db,
            conv_id,
            narrative="The team committed to SQLite as the local-first storage solution.",
        )

        conn = play_db._get_connection()
        memories = conn.execute(
            "SELECT id FROM memories WHERE conversation_id = ?", (conv_id,)
        ).fetchall()
        assert len(memories) >= 1

    def test_compression_entities_stored(self, rpc_db):
        """After compression, memory_entities table has rows linked to the conversation's memory."""
        from cairn import play_db

        start_resp = _rpc(rpc_db, req_id=1, method="lifecycle/conversations/start")
        conv_id = _result(start_resp)["conversation"]["id"]
        _rpc(
            rpc_db,
            req_id=2,
            method="lifecycle/conversations/add_message",
            params={
                "conversation_id": conv_id,
                "role": "user",
                "content": "Alex will handle the backend migration.",
            },
        )
        _rpc(
            rpc_db,
            req_id=3,
            method="lifecycle/conversations/close",
            params={"conversation_id": conv_id},
        )

        # Mock provider returns entities with a person entry
        mock_provider = _make_pipeline_mock(
            entities={
                "people": [
                    {"name": "Alex", "context": "backend migration", "relation": "colleague"}
                ]
            },
            narrative="Alex is taking ownership of the backend migration effort.",
        )

        from cairn.services.compression_manager import CompressionManager
        from cairn.services.compression_pipeline import (
            CompressionPipeline,
            format_transcript,
        )
        from cairn.services.conversation_service import ConversationService
        from cairn.services.memory_service import MemoryService

        service = ConversationService()
        messages = service.get_messages(conv_id)
        transcript = format_transcript(
            [{"role": m.role, "content": m.content} for m in messages]
        )

        with patch(
            "cairn.services.compression_pipeline.CompressionPipeline.generate_embedding",
            return_value=None,
        ):
            pipeline = CompressionPipeline(provider=mock_provider)
            conv = service.get_by_id(conv_id)
            result = pipeline.compress(
                transcript,
                conversation_date=conv.started_at if conv else "2026-03-28",
                message_count=len(messages),
            )

        service.start_compression(conv_id)

        with patch(
            "cairn.services.memory_service.get_embedding_service"
        ) as mock_emb_factory:
            mock_emb = MagicMock()
            mock_emb.find_similar.return_value = []
            mock_emb.embed.return_value = None
            mock_emb_factory.return_value = mock_emb

            memory_service = MemoryService()
            manager = CompressionManager(
                pipeline=pipeline, memory_service=memory_service
            )
            manager._store_results(conv_id, result)

        service.archive(conv_id)

        conn = play_db._get_connection()
        # Get the memory for this conversation
        memory_row = conn.execute(
            "SELECT id FROM memories WHERE conversation_id = ?", (conv_id,)
        ).fetchone()
        assert memory_row is not None

        entities = conn.execute(
            "SELECT entity_type FROM memory_entities WHERE memory_id = ?",
            (memory_row["id"],),
        ).fetchall()
        assert len(entities) >= 1
        entity_types = {r["entity_type"] for r in entities}
        assert "person" in entity_types

    def test_compression_narrative_stored(self, rpc_db):
        """After compression, conversation_summaries has a narrative row for the conversation."""
        from cairn import play_db

        start_resp = _rpc(rpc_db, req_id=1, method="lifecycle/conversations/start")
        conv_id = _result(start_resp)["conversation"]["id"]
        _rpc(
            rpc_db,
            req_id=2,
            method="lifecycle/conversations/add_message",
            params={
                "conversation_id": conv_id,
                "role": "user",
                "content": "I prefer async communication over sync meetings.",
            },
        )
        _rpc(
            rpc_db,
            req_id=3,
            method="lifecycle/conversations/close",
            params={"conversation_id": conv_id},
        )

        expected_narrative = "The user expressed a strong preference for async communication styles."
        self._run_compression(rpc_db, conv_id, narrative=expected_narrative)

        conn = play_db._get_connection()
        summary_row = conn.execute(
            "SELECT summary FROM conversation_summaries WHERE conversation_id = ?",
            (conv_id,),
        ).fetchone()
        assert summary_row is not None
        assert expected_narrative in summary_row["summary"]

    def test_compression_failure_rolls_back_state(self, rpc_db):
        """fail_compression() moves a compressing conversation back to ready_to_close."""
        from cairn import play_db
        from cairn.services.conversation_service import ConversationService

        start_resp = _rpc(rpc_db, req_id=1, method="lifecycle/conversations/start")
        conv_id = _result(start_resp)["conversation"]["id"]
        _rpc(
            rpc_db,
            req_id=2,
            method="lifecycle/conversations/close",
            params={"conversation_id": conv_id},
        )

        service = ConversationService()
        service.start_compression(conv_id)

        conn = play_db._get_connection()
        assert (
            conn.execute(
                "SELECT status FROM conversations WHERE id = ?", (conv_id,)
            ).fetchone()["status"]
            == "compressing"
        )

        service.fail_compression(conv_id)

        row = conn.execute(
            "SELECT status FROM conversations WHERE id = ?", (conv_id,)
        ).fetchone()
        assert row["status"] == "ready_to_close"


# =============================================================================
# Group 3: Turn Assessment (mock LLM, real DB)
# =============================================================================


class TestTurnAssessment:
    """TurnDeltaAssessor exercised synchronously with a mocked LLM provider."""

    def _make_assessor(self, *, intent: str, assessment: str = "NO_CHANGE", what: str = "") -> tuple:
        """Build a TurnDeltaAssessor with mocked provider and return (assessor, mock_provider)."""
        from cairn.services.turn_delta_assessor import TurnDeltaAssessor

        mock_provider = MagicMock()

        # chat_json is called twice: intent filter then (if sharing) knowledge detection
        # and optionally a third time for memory type classification
        intent_response = json.dumps({"intent": intent})
        assessment_response = json.dumps({"assessment": assessment, "what": what})
        type_response = json.dumps({"memory_type": "fact"})

        # chat_text is called for narrative compression
        mock_provider.chat_text.return_value = what or "User shared a new fact."
        mock_provider._model = "test-model"

        call_sequence = iter([intent_response, assessment_response, type_response])

        def side_effect(**kwargs: Any) -> str:
            try:
                return next(call_sequence)
            except StopIteration:
                return json.dumps({"assessment": "NO_CHANGE", "what": ""})

        mock_provider.chat_json.side_effect = side_effect

        with patch(
            "cairn.services.memory_service.get_embedding_service"
        ) as mock_emb_factory:
            mock_emb = MagicMock()
            mock_emb.find_similar.return_value = []
            mock_emb.embed.return_value = None
            mock_emb_factory.return_value = mock_emb

            from cairn.services.memory_service import MemoryService

            memory_service = MemoryService()

            # Patch pipeline provider too
            from cairn.services.compression_pipeline import CompressionPipeline

            pipeline = CompressionPipeline(provider=mock_provider)
            assessor = TurnDeltaAssessor(
                provider=mock_provider,
                memory_service=memory_service,
                compression_pipeline=pipeline,
            )

        return assessor, mock_provider

    def test_turn_assessment_no_change(self, rpc_db):
        """When LLM returns intent=asking, assessment is NO_CHANGE and no memory is created."""
        from cairn import play_db
        from cairn.services.conversation_service import ConversationService

        service = ConversationService()
        conv = service.start()

        mock_provider = MagicMock()
        mock_provider.chat_json.return_value = json.dumps({"intent": "asking"})
        mock_provider._model = "test-model"

        from cairn.services.memory_service import MemoryService
        from cairn.services.turn_delta_assessor import TurnDeltaAssessor

        with patch(
            "cairn.services.memory_service.get_embedding_service"
        ) as mock_emb_factory:
            mock_emb = MagicMock()
            mock_emb.find_similar.return_value = []
            mock_emb.embed.return_value = None
            mock_emb_factory.return_value = mock_emb

            assessor = TurnDeltaAssessor(
                provider=mock_provider,
                memory_service=MemoryService(),
            )
            result = assessor.assess_turn(
                conversation_id=conv.id,
                turn_position=0,
                user_message="What's on my calendar?",
                cairn_response="You have a meeting at 3pm.",
            )

        assert result.assessment == "NO_CHANGE"
        assert result.memory_id is None

        conn = play_db._get_connection()
        mem_count = conn.execute(
            "SELECT COUNT(*) FROM memories WHERE conversation_id = ?", (conv.id,)
        ).fetchone()[0]
        assert mem_count == 0

    def test_turn_assessment_creates_memory(self, rpc_db):
        """When LLM signals sharing + CREATE, a memory is persisted in the DB."""
        from cairn import play_db
        from cairn.services.conversation_service import ConversationService
        from cairn.services.memory_service import MemoryService
        from cairn.services.turn_delta_assessor import TurnDeltaAssessor

        service = ConversationService()
        conv = service.start()

        mock_provider = MagicMock()
        responses = iter(
            [
                json.dumps({"intent": "sharing"}),
                json.dumps({"assessment": "CREATE", "what": "user preference for async"}),
                json.dumps({"memory_type": "preference"}),
            ]
        )
        mock_provider.chat_json.side_effect = lambda **kwargs: next(responses)
        mock_provider.chat_text.return_value = "User prefers async communication over sync meetings."
        mock_provider._model = "test-model"

        from cairn.services.compression_pipeline import CompressionPipeline

        with patch(
            "cairn.services.memory_service.get_embedding_service"
        ) as mock_emb_factory:
            mock_emb = MagicMock()
            mock_emb.find_similar.return_value = []
            mock_emb.embed.return_value = None
            mock_emb_factory.return_value = mock_emb

            pipeline = CompressionPipeline(provider=mock_provider)
            memory_service = MemoryService()
            assessor = TurnDeltaAssessor(
                provider=mock_provider,
                memory_service=memory_service,
                compression_pipeline=pipeline,
            )
            result = assessor.assess_turn(
                conversation_id=conv.id,
                turn_position=1,
                user_message="I prefer async communication.",
                cairn_response="Noted, I'll keep that in mind.",
            )

        assert result.assessment == "CREATE"
        assert result.memory_id is not None

        conn = play_db._get_connection()
        mem = conn.execute(
            "SELECT id FROM memories WHERE conversation_id = ?", (conv.id,)
        ).fetchone()
        assert mem is not None
        assert mem["id"] == result.memory_id

    def test_turn_assessment_persisted_to_table(self, rpc_db):
        """assess_turn always writes an audit row to turn_assessments regardless of outcome."""
        from cairn import play_db
        from cairn.services.conversation_service import ConversationService
        from cairn.services.memory_service import MemoryService
        from cairn.services.turn_delta_assessor import TurnDeltaAssessor

        service = ConversationService()
        conv = service.start()

        mock_provider = MagicMock()
        mock_provider.chat_json.return_value = json.dumps({"intent": "asking"})
        mock_provider._model = "test-model"

        with patch(
            "cairn.services.memory_service.get_embedding_service"
        ) as mock_emb_factory:
            mock_emb = MagicMock()
            mock_emb.find_similar.return_value = []
            mock_emb_factory.return_value = mock_emb

            assessor = TurnDeltaAssessor(
                provider=mock_provider,
                memory_service=MemoryService(),
            )
            assessor.assess_turn(
                conversation_id=conv.id,
                turn_position=0,
                user_message="What time is it?",
                cairn_response="It is 2:30pm.",
            )

        conn = play_db._get_connection()
        row = conn.execute(
            "SELECT assessment, conversation_id, turn_position "
            "FROM turn_assessments WHERE conversation_id = ?",
            (conv.id,),
        ).fetchone()
        assert row is not None
        assert row["assessment"] == "NO_CHANGE"
        assert row["conversation_id"] == conv.id
        assert row["turn_position"] == 0


# =============================================================================
# Group 4: Full Lifecycle Integration
# =============================================================================


class TestFullLifecycleIntegration:
    """End-to-end lifecycle runs: start → messages → close → compress → archive."""

    def _compress_and_archive(self, conv_id: str, narrative: str = "Conversation summary.") -> None:
        """Helper: drive full compression + archive on a ready_to_close conversation."""
        from cairn.services.compression_manager import CompressionManager
        from cairn.services.compression_pipeline import (
            CompressionPipeline,
            format_transcript,
        )
        from cairn.services.conversation_service import ConversationService
        from cairn.services.memory_service import MemoryService

        service = ConversationService()
        messages = service.get_messages(conv_id)
        transcript = format_transcript(
            [{"role": m.role, "content": m.content} for m in messages]
        )
        mock_provider = _make_pipeline_mock(narrative=narrative)

        with patch(
            "cairn.services.compression_pipeline.CompressionPipeline.generate_embedding",
            return_value=None,
        ):
            pipeline = CompressionPipeline(provider=mock_provider)
            conv = service.get_by_id(conv_id)
            result = pipeline.compress(
                transcript,
                conversation_date=conv.started_at if conv else "2026-03-28",
                message_count=len(messages),
            )

        service.start_compression(conv_id)

        with patch(
            "cairn.services.memory_service.get_embedding_service"
        ) as mock_emb_factory:
            mock_emb = MagicMock()
            mock_emb.find_similar.return_value = []
            mock_emb.embed.return_value = None
            mock_emb_factory.return_value = mock_emb

            manager = CompressionManager(
                pipeline=pipeline, memory_service=MemoryService()
            )
            manager._store_results(conv_id, result)

        service.archive(conv_id)

    def test_full_lifecycle_start_to_archive(self, rpc_db):
        """start → add messages → close → compress (mock LLM) → archive yields status='archived'."""
        from cairn import play_db

        start_resp = _rpc(rpc_db, req_id=1, method="lifecycle/conversations/start")
        conv_id = _result(start_resp)["conversation"]["id"]

        _rpc(
            rpc_db,
            req_id=2,
            method="lifecycle/conversations/add_message",
            params={"conversation_id": conv_id, "role": "user", "content": "Planning sprint."},
        )
        _rpc(
            rpc_db,
            req_id=3,
            method="lifecycle/conversations/add_message",
            params={"conversation_id": conv_id, "role": "cairn", "content": "Understood."},
        )
        _rpc(
            rpc_db,
            req_id=4,
            method="lifecycle/conversations/close",
            params={"conversation_id": conv_id},
        )

        self._compress_and_archive(conv_id, narrative="Sprint planning discussion captured.")

        conn = play_db._get_connection()
        row = conn.execute(
            "SELECT status, archived_at FROM conversations WHERE id = ?", (conv_id,)
        ).fetchone()
        assert row["status"] == "archived"
        assert row["archived_at"] is not None

    def test_lifecycle_with_resume_and_rearchive(self, rpc_db):
        """start → close → resume → add message → close → compress → archive completes cleanly."""
        from cairn import play_db

        start_resp = _rpc(rpc_db, req_id=1, method="lifecycle/conversations/start")
        conv_id = _result(start_resp)["conversation"]["id"]

        _rpc(
            rpc_db,
            req_id=2,
            method="lifecycle/conversations/add_message",
            params={"conversation_id": conv_id, "role": "user", "content": "First message."},
        )
        _rpc(
            rpc_db,
            req_id=3,
            method="lifecycle/conversations/close",
            params={"conversation_id": conv_id},
        )
        _rpc(
            rpc_db,
            req_id=4,
            method="lifecycle/conversations/resume",
            params={"conversation_id": conv_id},
        )
        _rpc(
            rpc_db,
            req_id=5,
            method="lifecycle/conversations/add_message",
            params={"conversation_id": conv_id, "role": "user", "content": "Second message after resume."},
        )
        _rpc(
            rpc_db,
            req_id=6,
            method="lifecycle/conversations/close",
            params={"conversation_id": conv_id},
        )

        self._compress_and_archive(conv_id, narrative="Resume-then-close cycle archived.")

        conn = play_db._get_connection()
        row = conn.execute(
            "SELECT status, message_count FROM conversations WHERE id = ?", (conv_id,)
        ).fetchone()
        assert row["status"] == "archived"
        assert row["message_count"] == 2

    def test_archived_conversation_appears_in_list(self, rpc_db):
        """After full lifecycle, listing with status='archived' includes the conversation."""
        start_resp = _rpc(rpc_db, req_id=1, method="lifecycle/conversations/start")
        conv_id = _result(start_resp)["conversation"]["id"]

        _rpc(
            rpc_db,
            req_id=2,
            method="lifecycle/conversations/add_message",
            params={"conversation_id": conv_id, "role": "user", "content": "Archive me."},
        )
        _rpc(
            rpc_db,
            req_id=3,
            method="lifecycle/conversations/close",
            params={"conversation_id": conv_id},
        )
        self._compress_and_archive(conv_id, narrative="To be listed.")

        list_resp = _rpc(
            rpc_db,
            req_id=4,
            method="lifecycle/conversations/list",
            params={"status": "archived"},
        )
        conversations = _result(list_resp)["conversations"]
        ids = [c["id"] for c in conversations]
        assert conv_id in ids

    def test_conversation_detail_after_archive(self, rpc_db):
        """After archive, detail endpoint returns messages, memories, and a summary."""
        start_resp = _rpc(rpc_db, req_id=1, method="lifecycle/conversations/start")
        conv_id = _result(start_resp)["conversation"]["id"]

        _rpc(
            rpc_db,
            req_id=2,
            method="lifecycle/conversations/add_message",
            params={"conversation_id": conv_id, "role": "user", "content": "Detail check."},
        )
        _rpc(
            rpc_db,
            req_id=3,
            method="lifecycle/conversations/close",
            params={"conversation_id": conv_id},
        )
        expected_summary = "The user wanted to verify detail retrieval after archive."
        self._compress_and_archive(conv_id, narrative=expected_summary)

        detail_resp = _rpc(
            rpc_db,
            req_id=4,
            method="lifecycle/conversations/detail",
            params={"conversation_id": conv_id},
        )
        detail = _result(detail_resp)
        assert detail["conversation"]["id"] == conv_id
        assert detail["conversation"]["status"] == "archived"
        assert len(detail["messages"]) == 1
        assert len(detail["memories"]) >= 1
        assert detail["summary"] == expected_summary


# =============================================================================
# Group 5: Failure Injection
# =============================================================================


class TestFailureInjection:
    """Edge cases and invalid operation sequences."""

    def test_close_nonexistent_conversation_returns_error(self, rpc_db):
        """Closing a conversation ID that does not exist produces an RPC error response."""
        resp = _rpc(
            rpc_db,
            req_id=1,
            method="lifecycle/conversations/close",
            params={"conversation_id": "does-not-exist"},
        )
        # The rpc_handler decorator converts ConversationError → RpcError → error in resp
        assert "error" in resp

    def test_add_message_to_closed_conversation_fails(self, rpc_db):
        """Adding a message to a ready_to_close conversation produces an RPC error response."""
        start_resp = _rpc(rpc_db, req_id=1, method="lifecycle/conversations/start")
        conv_id = _result(start_resp)["conversation"]["id"]

        _rpc(
            rpc_db,
            req_id=2,
            method="lifecycle/conversations/close",
            params={"conversation_id": conv_id},
        )

        resp = _rpc(
            rpc_db,
            req_id=3,
            method="lifecycle/conversations/add_message",
            params={
                "conversation_id": conv_id,
                "role": "user",
                "content": "Too late.",
            },
        )
        assert "error" in resp

    def test_double_close_fails(self, rpc_db):
        """Closing an already-closed (ready_to_close) conversation produces an RPC error response."""
        start_resp = _rpc(rpc_db, req_id=1, method="lifecycle/conversations/start")
        conv_id = _result(start_resp)["conversation"]["id"]

        _rpc(
            rpc_db,
            req_id=2,
            method="lifecycle/conversations/close",
            params={"conversation_id": conv_id},
        )

        resp = _rpc(
            rpc_db,
            req_id=3,
            method="lifecycle/conversations/close",
            params={"conversation_id": conv_id},
        )
        assert "error" in resp
