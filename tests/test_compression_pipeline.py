"""Tests for the compression pipeline and background manager.

Uses mocked Ollama provider to avoid requiring local LLM for tests.
"""
from __future__ import annotations

import json
import time
import pytest
from pathlib import Path
from unittest.mock import MagicMock

from reos.play_db import init_db, close_connection, _get_connection
from reos.services.compression_pipeline import (
    CompressionPipeline,
    ExtractionResult,
    format_transcript,
)
from reos.services.compression_manager import (
    CompressionManager,
    CompressionStatus,
)
from reos.services.conversation_service import ConversationService


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def conv_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Set up a fresh play database for compression tests."""
    data_dir = tmp_path / "reos-data"
    data_dir.mkdir()
    monkeypatch.setenv("REOS_DATA_DIR", str(data_dir))

    import reos.play_db as play_db

    play_db.close_connection()
    play_db.init_db()

    yield data_dir

    play_db.close_connection()


@pytest.fixture
def mock_provider():
    """Mock OllamaProvider that returns predictable JSON for each call stage.

    chat_json is called twice per full compress(): once for entity extraction,
    once for state delta detection. Both calls return valid JSON dicts.
    chat_text is called once for narrative synthesis.
    """
    provider = MagicMock()

    entity_response = json.dumps({
        "decisions": [{"what": "Use SQLite", "why": "Local first"}],
        "tasks": [{"description": "Build schema", "status": "decided", "priority": "high"}],
    })
    delta_response = json.dumps({
        "new_open_threads": [{"thread": "schema design", "act": "Project"}],
    })

    # Alternate between entity extraction and state delta responses.
    call_count = {"n": 0}

    def json_side_effect(*, system, user, **kw):
        n = call_count["n"]
        call_count["n"] += 1
        if n % 2 == 0:
            return entity_response
        return delta_response

    provider.chat_json.side_effect = json_side_effect
    provider.chat_text.return_value = (
        "Decided to use SQLite for local-first storage. "
        "The schema design is the immediate next step."
    )
    provider._model = "llama3.2:3b"

    return provider


@pytest.fixture
def mock_embedder():
    """Mock EmbeddingService that returns a fixed-size byte blob."""
    embedder = MagicMock()
    embedder.embed.return_value = b"\x00" * (384 * 4)  # 384 float32s
    return embedder


@pytest.fixture
def pipeline(mock_provider, mock_embedder):
    """CompressionPipeline with mocked provider and embedder."""
    return CompressionPipeline(provider=mock_provider, embedding_service=mock_embedder)


# =============================================================================
# TestFormatTranscript
# =============================================================================


class TestFormatTranscript:
    """Tests for the format_transcript utility."""

    def test_formats_user_and_assistant_messages(self):
        """Each message appears as [role]: content in the output."""
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "cairn", "content": "Hi there"},
        ]
        result = format_transcript(messages)
        assert "[user]: Hello" in result
        assert "[cairn]: Hi there" in result

    def test_messages_separated_by_double_newline(self):
        """Messages are joined with a blank line between them."""
        messages = [
            {"role": "user", "content": "First"},
            {"role": "cairn", "content": "Second"},
        ]
        result = format_transcript(messages)
        assert "[user]: First\n\n[cairn]: Second" == result

    def test_empty_message_list_returns_empty_string(self):
        """An empty list produces an empty string, not an error."""
        assert format_transcript([]) == ""

    def test_single_message_has_no_separator(self):
        """A single message produces just the formatted line."""
        messages = [{"role": "user", "content": "Solo"}]
        result = format_transcript(messages)
        assert result == "[user]: Solo"

    def test_unknown_role_is_preserved(self):
        """The role label is taken verbatim from the dict key."""
        messages = [{"role": "system", "content": "Context"}]
        result = format_transcript(messages)
        assert "[system]: Context" in result

    def test_missing_role_defaults_to_unknown(self):
        """A message without a role key uses 'unknown' as the label."""
        messages = [{"content": "No role here"}]
        result = format_transcript(messages)
        assert "[unknown]:" in result

    def test_missing_content_defaults_to_empty(self):
        """A message without a content key produces an empty body."""
        messages = [{"role": "user"}]
        result = format_transcript(messages)
        assert "[user]: " in result


# =============================================================================
# TestExtractionResult
# =============================================================================


class TestExtractionResult:
    """Tests for the ExtractionResult data class and its flattening helpers."""

    def test_entity_list_flattens_decisions_and_tasks(self):
        """entity_list returns one entry per entity across all categories."""
        result = ExtractionResult(
            entities={
                "decisions": [{"what": "test", "why": "because"}],
                "tasks": [{"description": "do thing", "status": "decided", "priority": "high"}],
            }
        )
        flat = result.entity_list()
        assert len(flat) == 2
        types = {e["entity_type"] for e in flat}
        assert types == {"decision", "task"}

    def test_entity_list_maps_people_to_person_type(self):
        """The 'people' category maps to entity_type 'person'."""
        result = ExtractionResult(
            entities={"people": [{"name": "Alice", "context": "colleague", "relation": "peer"}]}
        )
        flat = result.entity_list()
        assert len(flat) == 1
        assert flat[0]["entity_type"] == "person"

    def test_entity_list_maps_waiting_on_type(self):
        """The 'waiting_on' category maps to entity_type 'waiting_on'."""
        result = ExtractionResult(
            entities={"waiting_on": [{"who": "Bob", "what": "review", "since": "today"}]}
        )
        flat = result.entity_list()
        assert flat[0]["entity_type"] == "waiting_on"

    def test_entity_list_preserves_entity_data(self):
        """Each entry in entity_list carries the original dict as 'entity_data'."""
        original = {"what": "Use Redis", "why": "Speed"}
        result = ExtractionResult(entities={"decisions": [original]})
        flat = result.entity_list()
        assert flat[0]["entity_data"] == original

    def test_entity_list_empty_when_no_entities(self):
        """entity_list returns an empty list when entities dict is empty."""
        result = ExtractionResult()
        assert result.entity_list() == []

    def test_entity_list_ignores_unknown_categories(self):
        """Categories not in the type_mapping are silently skipped."""
        result = ExtractionResult(entities={"unknown_category": [{"foo": "bar"}]})
        assert result.entity_list() == []

    def test_delta_list_flattens_waiting_ons_and_threads(self):
        """delta_list returns one entry per delta across all delta categories."""
        result = ExtractionResult(
            state_deltas={
                "new_waiting_ons": [{"who": "Alex", "what": "review"}],
                "resolved_threads": [{"thread": "design decision"}],
            }
        )
        flat = result.delta_list()
        assert len(flat) == 2
        types = {d["delta_type"] for d in flat}
        assert types == {"new_waiting_on", "resolved_thread"}

    def test_delta_list_empty_when_no_deltas(self):
        """delta_list returns an empty list when state_deltas is empty."""
        result = ExtractionResult()
        assert result.delta_list() == []

    def test_delta_list_preserves_delta_data(self):
        """Each entry in delta_list carries the original dict as 'delta_data'."""
        original = {"thread": "auth redesign", "act": "Security"}
        result = ExtractionResult(
            state_deltas={"new_open_threads": [original]}
        )
        flat = result.delta_list()
        assert flat[0]["delta_data"] == original

    def test_default_fields_are_falsy(self):
        """A freshly created ExtractionResult has empty/zero default fields."""
        result = ExtractionResult()
        assert result.narrative == ""
        assert result.entities == {}
        assert result.state_deltas == {}
        assert result.embedding is None
        assert result.passes == 0
        assert result.confidence == 0.0


# =============================================================================
# TestCompressionPipeline
# =============================================================================


class TestCompressionPipeline:
    """Tests for the 4-stage CompressionPipeline with mocked provider."""

    def test_full_compress_returns_extraction_result(self, pipeline):
        """compress() returns an ExtractionResult with all fields populated."""
        result = pipeline.compress(
            "[user]: Let's use SQLite\n\n[cairn]: Good choice",
            conversation_date="2026-02-22",
            message_count=2,
        )
        assert isinstance(result, ExtractionResult)

    def test_full_compress_populates_entities(self, pipeline):
        """compress() calls entity extraction and stores results in entities."""
        result = pipeline.compress("[user]: Decided to use SQLite", message_count=1)
        assert result.entities != {}

    def test_full_compress_populates_narrative(self, pipeline):
        """compress() calls narrative synthesis and stores result."""
        result = pipeline.compress("[user]: We made a decision", message_count=1)
        assert result.narrative != ""

    def test_full_compress_records_model_name(self, pipeline, mock_provider):
        """compress() captures the provider's model name in model_used."""
        result = pipeline.compress("[user]: test", message_count=1)
        assert result.model_used == "llama3.2:3b"

    def test_full_compress_records_duration(self, pipeline):
        """compress() records a non-negative duration in milliseconds."""
        result = pipeline.compress("[user]: test", message_count=1)
        assert result.duration_ms >= 0

    def test_full_compress_pass_count_at_least_three(self, pipeline):
        """compress() increments passes for entity, narrative, and delta stages."""
        result = pipeline.compress("[user]: test", message_count=1)
        assert result.passes >= 3

    def test_full_compress_pass_count_four_when_embedding_succeeds(self, pipeline):
        """compress() counts four passes when embedding stage succeeds."""
        result = pipeline.compress("[user]: test", message_count=1)
        # embedding stage runs since mock_embedder is provided and narrative is non-empty
        assert result.passes == 4

    def test_full_compress_embedding_populated(self, pipeline):
        """compress() stores the embedding bytes from the embedder."""
        result = pipeline.compress("[user]: test", message_count=1)
        assert result.embedding is not None
        assert len(result.embedding) == 384 * 4

    def test_extract_entities_returns_dict_from_json(self, pipeline):
        """extract_entities parses JSON from provider and returns a dict."""
        entities = pipeline.extract_entities("[user]: Decided to use SQLite")
        assert isinstance(entities, dict)
        assert "decisions" in entities

    def test_compress_narrative_returns_non_empty_string(self, pipeline):
        """compress_narrative returns the stripped text from the provider."""
        narrative = pipeline.compress_narrative(
            {"decisions": [{"what": "Use SQLite", "why": "local"}]},
            conversation_date="2026-02-22",
            message_count=2,
        )
        assert isinstance(narrative, str)
        assert len(narrative) > 0

    def test_detect_state_deltas_returns_dict(self, pipeline):
        """detect_state_deltas parses JSON response and returns a dict."""
        deltas = pipeline.detect_state_deltas(
            {"tasks": [{"description": "build schema", "status": "decided", "priority": "high"}]}
        )
        assert isinstance(deltas, dict)

    def test_generate_embedding_returns_bytes(self, pipeline):
        """generate_embedding returns the byte blob from the embedder."""
        embedding = pipeline.generate_embedding("Test narrative text")
        assert isinstance(embedding, bytes)
        assert len(embedding) == 384 * 4

    def test_generate_embedding_returns_none_for_empty_narrative(self, pipeline):
        """generate_embedding short-circuits and returns None when narrative is empty."""
        embedding = pipeline.generate_embedding("")
        assert embedding is None

    def test_confidence_above_zero_when_entities_and_narrative_present(self, pipeline):
        """compress() produces non-zero confidence when both entities and narrative exist."""
        result = pipeline.compress("[user]: We decided something", message_count=1)
        assert result.confidence > 0.0

    def test_confidence_at_most_one(self, pipeline):
        """compress() caps confidence at 1.0."""
        result = pipeline.compress("[user]: test", message_count=1)
        assert result.confidence <= 1.0

    def test_confidence_zero_when_no_entities_and_no_narrative(self, mock_provider, mock_embedder):
        """_estimate_confidence returns 0.0 when entities and narrative are both empty."""
        mock_provider.chat_json.side_effect = lambda *, system, user, **kw: json.dumps({})
        mock_provider.chat_text.return_value = ""
        p = CompressionPipeline(provider=mock_provider, embedding_service=mock_embedder)
        result = p.compress("[user]: silent", message_count=1)
        assert result.confidence == 0.0

    def test_entity_extraction_graceful_on_provider_exception(self, mock_provider, mock_embedder):
        """extract_entities returns an empty dict when the provider raises."""
        mock_provider.chat_json.side_effect = Exception("Connection refused")
        p = CompressionPipeline(provider=mock_provider, embedding_service=mock_embedder)
        entities = p.extract_entities("any transcript")
        assert entities == {}

    def test_narrative_graceful_on_provider_exception(self, mock_provider, mock_embedder):
        """compress_narrative returns an empty string when the provider raises."""
        mock_provider.chat_text.side_effect = Exception("LLM unavailable")
        p = CompressionPipeline(provider=mock_provider, embedding_service=mock_embedder)
        narrative = p.compress_narrative({"decisions": []})
        assert narrative == ""

    def test_state_delta_graceful_on_provider_exception(self, mock_provider, mock_embedder):
        """detect_state_deltas returns an empty dict when the provider raises."""
        # Make all chat_json calls fail
        mock_provider.chat_json.side_effect = Exception("Network error")
        p = CompressionPipeline(provider=mock_provider, embedding_service=mock_embedder)
        deltas = p.detect_state_deltas({"tasks": []})
        assert deltas == {}

    def test_entity_extraction_graceful_on_invalid_json(self, mock_provider, mock_embedder):
        """extract_entities returns empty dict when provider returns malformed JSON."""
        mock_provider.chat_json.side_effect = lambda *, system, user, **kw: "not valid json {"
        p = CompressionPipeline(provider=mock_provider, embedding_service=mock_embedder)
        entities = p.extract_entities("any transcript")
        assert entities == {}

    def test_entity_extraction_graceful_on_non_dict_json(self, mock_provider, mock_embedder):
        """extract_entities returns empty dict when provider returns a JSON array instead of object."""
        mock_provider.chat_json.side_effect = lambda *, system, user, **kw: json.dumps([1, 2, 3])
        p = CompressionPipeline(provider=mock_provider, embedding_service=mock_embedder)
        entities = p.extract_entities("any transcript")
        assert entities == {}

    def test_embedding_skipped_when_no_embedder_and_no_importable_service(
        self, mock_provider
    ):
        """generate_embedding returns None when no embedder is set and import fails."""
        import sys
        # Temporarily hide the embeddings module to simulate missing sentence-transformers
        saved = sys.modules.get("reos.memory.embeddings")
        sys.modules["reos.memory.embeddings"] = None  # type: ignore[assignment]
        try:
            p = CompressionPipeline(provider=mock_provider, embedding_service=None)
            result = p.generate_embedding("Some narrative")
            assert result is None
        finally:
            if saved is None:
                sys.modules.pop("reos.memory.embeddings", None)
            else:
                sys.modules["reos.memory.embeddings"] = saved


# =============================================================================
# TestCompressionStatus
# =============================================================================


class TestCompressionStatus:
    """Tests for the CompressionStatus dataclass."""

    def test_to_dict_includes_all_fields(self):
        """to_dict returns a dict with all four status fields."""
        status = CompressionStatus(
            conversation_id="conv-abc",
            state="completed",
            error=None,
            result_memory_ids=["mem-123"],
        )
        d = status.to_dict()
        assert d["conversation_id"] == "conv-abc"
        assert d["state"] == "completed"
        assert d["error"] is None
        assert d["result_memory_ids"] == ["mem-123"]

    def test_to_dict_with_error_field(self):
        """to_dict serializes the error field when compression failed."""
        status = CompressionStatus(
            conversation_id="conv-xyz",
            state="failed",
            error="LLM down",
        )
        d = status.to_dict()
        assert d["error"] == "LLM down"
        assert d["result_memory_ids"] is None


# =============================================================================
# TestCompressionManager
# =============================================================================


class TestCompressionManager:
    """Tests for the background CompressionManager."""

    def test_get_status_unknown_conversation_returns_none(self, conv_db):
        """get_status returns None for a conversation that was never submitted."""
        manager = CompressionManager()
        assert manager.get_status("nonexistent-conv-id") is None

    def test_submit_returns_queued_status(self, conv_db):
        """submit() immediately returns a CompressionStatus with state='queued'."""
        svc = ConversationService()
        conv = svc.start()
        svc.add_message(conv.id, "user", "Hello")
        svc.close(conv.id)

        manager = CompressionManager()
        status = manager.submit(conv.id)
        assert status.state == "queued"
        assert status.conversation_id == conv.id

    def test_submit_registers_status_for_polling(self, conv_db):
        """After submit(), get_status returns the initial queued status."""
        svc = ConversationService()
        conv = svc.start()
        svc.add_message(conv.id, "user", "Hello")
        svc.close(conv.id)

        manager = CompressionManager()
        manager.submit(conv.id)
        status = manager.get_status(conv.id)
        assert status is not None
        assert status.state == "queued"

    def test_full_pipeline_completes_and_stores_memory(self, conv_db, mock_provider, mock_embedder):
        """Full integration: close a conversation, compress it, verify DB row exists."""
        svc = ConversationService()
        conv = svc.start()
        svc.add_message(conv.id, "user", "Let's use SQLite for storage")
        svc.add_message(conv.id, "cairn", "Good choice for local-first")
        svc.close(conv.id)

        pipeline = CompressionPipeline(provider=mock_provider, embedding_service=mock_embedder)
        manager = CompressionManager(pipeline=pipeline)
        manager.start()

        try:
            manager.submit(conv.id)

            # Poll for completion with a 5-second ceiling.
            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline:
                status = manager.get_status(conv.id)
                if status and status.state in ("completed", "failed"):
                    break
                time.sleep(0.1)

            status = manager.get_status(conv.id)
            assert status is not None
            assert status.state == "completed", f"Expected completed, got: {status.state} / {status.error}"

        finally:
            manager.stop()

    def test_full_pipeline_stores_memory_row_in_db(self, conv_db, mock_provider, mock_embedder):
        """After successful compression, a memory row exists in the memories table."""
        svc = ConversationService()
        conv = svc.start()
        svc.add_message(conv.id, "user", "Decided to use SQLite")
        svc.add_message(conv.id, "cairn", "Agreed — local first.")
        svc.close(conv.id)

        pipeline = CompressionPipeline(provider=mock_provider, embedding_service=mock_embedder)
        manager = CompressionManager(pipeline=pipeline)
        manager.start()

        try:
            manager.submit(conv.id)

            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline:
                status = manager.get_status(conv.id)
                if status and status.state in ("completed", "failed"):
                    break
                time.sleep(0.1)

            assert manager.get_status(conv.id).state == "completed"

            conn = _get_connection()
            cursor = conn.execute(
                "SELECT * FROM memories WHERE conversation_id = ?", (conv.id,)
            )
            rows = cursor.fetchall()
            assert len(rows) == 1
            assert rows[0]["status"] == "pending_review"
            assert rows[0]["signal_count"] == 1

        finally:
            manager.stop()

    def test_full_pipeline_stores_entity_rows_in_db(self, conv_db, mock_provider, mock_embedder):
        """After successful compression, at least one memory_entities row exists."""
        svc = ConversationService()
        conv = svc.start()
        svc.add_message(conv.id, "user", "We decided on SQLite")
        svc.close(conv.id)

        pipeline = CompressionPipeline(provider=mock_provider, embedding_service=mock_embedder)
        manager = CompressionManager(pipeline=pipeline)
        manager.start()

        try:
            manager.submit(conv.id)

            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline:
                status = manager.get_status(conv.id)
                if status and status.state in ("completed", "failed"):
                    break
                time.sleep(0.1)

            assert manager.get_status(conv.id).state == "completed"

            conn = _get_connection()
            memory_row = conn.execute(
                "SELECT id FROM memories WHERE conversation_id = ?", (conv.id,)
            ).fetchone()
            assert memory_row is not None

            count = conn.execute(
                "SELECT COUNT(*) FROM memory_entities WHERE memory_id = ?",
                (memory_row["id"],),
            ).fetchone()[0]
            assert count > 0

        finally:
            manager.stop()

    def test_full_pipeline_returns_memory_ids(self, conv_db, mock_provider, mock_embedder):
        """status.result_memory_ids is non-empty after successful compression."""
        svc = ConversationService()
        conv = svc.start()
        svc.add_message(conv.id, "user", "Some decision was made")
        svc.close(conv.id)

        pipeline = CompressionPipeline(provider=mock_provider, embedding_service=mock_embedder)
        manager = CompressionManager(pipeline=pipeline)
        manager.start()

        try:
            manager.submit(conv.id)

            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline:
                status = manager.get_status(conv.id)
                if status and status.state in ("completed", "failed"):
                    break
                time.sleep(0.1)

            status = manager.get_status(conv.id)
            assert status.state == "completed"
            assert status.result_memory_ids is not None
            assert len(status.result_memory_ids) > 0

        finally:
            manager.stop()

    def test_failed_compression_resets_conversation_to_ready_to_close(self, conv_db):
        """When compress() raises an unhandled exception, the conversation rolls back to ready_to_close.

        The pipeline gracefully absorbs provider errors (returns empty structs), so to
        exercise the failure branch in the manager we must make compress() itself raise.
        """
        from unittest.mock import patch

        svc = ConversationService()
        conv = svc.start()
        svc.add_message(conv.id, "user", "Test message")
        svc.close(conv.id)

        pipeline = CompressionPipeline()

        manager = CompressionManager(pipeline=pipeline)
        manager.start()

        try:
            # Patch compress() on the pipeline instance to always blow up.
            with patch.object(pipeline, "compress", side_effect=RuntimeError("pipeline exploded")):
                manager.submit(conv.id)

                deadline = time.monotonic() + 5.0
                while time.monotonic() < deadline:
                    status = manager.get_status(conv.id)
                    if status and status.state == "failed":
                        break
                    time.sleep(0.1)

            status = manager.get_status(conv.id)
            assert status is not None
            assert status.state == "failed"
            assert status.error is not None

            # Conversation must be retryable — rolled back to ready_to_close.
            updated = svc.get_by_id(conv.id)
            assert updated is not None
            assert updated.status == "ready_to_close"

        finally:
            manager.stop()

    def test_failed_compression_status_has_error_message(self, conv_db):
        """A failed job records the exception message in status.error."""
        from unittest.mock import patch

        svc = ConversationService()
        conv = svc.start()
        svc.add_message(conv.id, "user", "Test")
        svc.close(conv.id)

        pipeline = CompressionPipeline()
        manager = CompressionManager(pipeline=pipeline)
        manager.start()

        try:
            with patch.object(
                pipeline, "compress", side_effect=RuntimeError("Sentinel error text")
            ):
                manager.submit(conv.id)

                deadline = time.monotonic() + 5.0
                while time.monotonic() < deadline:
                    status = manager.get_status(conv.id)
                    if status and status.state == "failed":
                        break
                    time.sleep(0.1)

            status = manager.get_status(conv.id)
            assert status.state == "failed"
            assert status.error is not None

        finally:
            manager.stop()

    def test_status_transitions_queued_then_completed(self, conv_db, mock_provider, mock_embedder):
        """Status is 'queued' immediately after submit, then 'completed' after processing."""
        svc = ConversationService()
        conv = svc.start()
        svc.add_message(conv.id, "user", "Let's talk decisions")
        svc.close(conv.id)

        pipeline = CompressionPipeline(provider=mock_provider, embedding_service=mock_embedder)
        manager = CompressionManager(pipeline=pipeline)

        # Submit before starting worker — status must be queued immediately.
        initial_status = manager.submit(conv.id)
        assert initial_status.state == "queued"

        manager.start()
        try:
            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline:
                s = manager.get_status(conv.id)
                if s and s.state in ("completed", "failed"):
                    break
                time.sleep(0.1)

            final = manager.get_status(conv.id)
            assert final is not None
            assert final.state == "completed"

        finally:
            manager.stop()

    def test_manager_stop_joins_thread(self, conv_db, mock_provider, mock_embedder):
        """stop() waits for the worker thread to terminate cleanly."""
        pipeline = CompressionPipeline(provider=mock_provider, embedding_service=mock_embedder)
        manager = CompressionManager(pipeline=pipeline)
        manager.start()

        manager.stop()

        assert manager._thread is None

    def test_double_start_is_idempotent(self, conv_db, mock_provider, mock_embedder):
        """Calling start() twice does not spawn a second thread."""
        pipeline = CompressionPipeline(provider=mock_provider, embedding_service=mock_embedder)
        manager = CompressionManager(pipeline=pipeline)

        try:
            manager.start()
            thread_one = manager._thread
            manager.start()  # second call — should be a no-op
            assert manager._thread is thread_one
        finally:
            manager.stop()

    def test_no_messages_conversation_marks_failed(self, conv_db, mock_provider, mock_embedder):
        """A conversation with zero messages results in state='failed', not a crash."""
        svc = ConversationService()
        conv = svc.start()
        # Close without adding any messages.
        svc.close(conv.id)

        pipeline = CompressionPipeline(provider=mock_provider, embedding_service=mock_embedder)
        manager = CompressionManager(pipeline=pipeline)
        manager.start()

        try:
            manager.submit(conv.id)

            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline:
                status = manager.get_status(conv.id)
                if status and status.state in ("completed", "failed"):
                    break
                time.sleep(0.1)

            status = manager.get_status(conv.id)
            assert status is not None
            assert status.state == "failed"

        finally:
            manager.stop()
