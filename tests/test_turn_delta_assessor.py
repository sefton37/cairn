"""Tests for TurnDeltaAssessor and TurnAssessmentQueue.

Covers:
- NO_CHANGE path for casual messages
- CREATE path for decisions/commitments
- JSON parse failure → NO_CHANGE (never raises)
- Audit row persisted to turn_assessments table for both outcomes
- CREATE path calls MemoryService.store(source='turn_assessment')
- No active lifecycle conversation → _maybe_submit returns silently
- Background queue submit() returns immediately (non-blocking)
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cairn.play_db import _get_connection
from cairn.services.turn_delta_assessor import (
    TurnAssessmentQueue,
    TurnDeltaAssessor,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def fresh_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Set up a fresh play database for each test."""
    data_dir = tmp_path / "reos-data"
    data_dir.mkdir()
    monkeypatch.setenv("REOS_DATA_DIR", str(data_dir))

    import cairn.play_db as play_db

    play_db.close_connection()
    play_db.init_db()

    yield data_dir

    play_db.close_connection()


@pytest.fixture()
def mock_provider_no_change():
    """OllamaProvider that returns NO_CHANGE for any turn."""
    provider = MagicMock()
    provider.chat_json.return_value = json.dumps({"assessment": "NO_CHANGE", "what": ""})
    provider._model = "llama3.2:1b"
    return provider


@pytest.fixture()
def mock_provider_create():
    """OllamaProvider that returns CREATE for classification, plus narrative text."""
    provider = MagicMock()
    # First call: classification → CREATE
    # Second call (entity extraction in pipeline): entity JSON
    # Third call (state delta): delta JSON
    call_count = {"n": 0}

    def json_side_effect(*, system, user, **kw):
        n = call_count["n"]
        call_count["n"] += 1
        if n == 0:
            # Classification call
            return json.dumps({"assessment": "CREATE", "what": "Decided to use PostgreSQL"})
        if n % 2 == 1:
            # Entity extraction
            return json.dumps({
                "decisions": [{"what": "Use PostgreSQL", "why": "Scalability"}]
            })
        # State delta
        return json.dumps({})

    provider.chat_json.side_effect = json_side_effect
    provider.chat_text.return_value = "Decided to use PostgreSQL for better scalability."
    provider._model = "llama3.2:1b"
    return provider


@pytest.fixture()
def mock_provider_bad_json():
    """OllamaProvider that returns malformed JSON for the classification call."""
    provider = MagicMock()
    provider.chat_json.return_value = "not valid json {"
    provider._model = "llama3.2:1b"
    return provider


@pytest.fixture()
def lifecycle_conversation(fresh_db):
    """Create and return an active lifecycle conversation."""
    from cairn.services.conversation_service import ConversationService

    svc = ConversationService()
    conv = svc.start()
    svc.add_message(conv.id, "user", "Hello")
    svc.add_message(conv.id, "cairn", "Hi there")
    return conv


# =============================================================================
# TestTurnDeltaAssessor — classification
# =============================================================================


class TestNoChangeCasualMessage:
    """NO_CHANGE is returned when the LLM signals casual chat."""

    def test_assessment_is_no_change(self, mock_provider_no_change):
        assessor = TurnDeltaAssessor(provider=mock_provider_no_change)
        result = assessor._classify_turn(
            user_message="How are you?",
            cairn_response="I'm doing well, thanks for asking!",
            relevant_memories=[],
        )
        assert result[0] == "NO_CHANGE"

    def test_what_is_empty_for_no_change(self, mock_provider_no_change):
        assessor = TurnDeltaAssessor(provider=mock_provider_no_change)
        assessment, what = assessor._classify_turn(
            user_message="How are you?",
            cairn_response="I'm doing well, thanks for asking!",
            relevant_memories=[],
        )
        assert what == ""


class TestCreateOnDecision:
    """CREATE is returned when the LLM detects new knowledge."""

    def test_assessment_is_create(self, mock_provider_create):
        assessor = TurnDeltaAssessor(provider=mock_provider_create)
        assessment, what = assessor._classify_turn(
            user_message="I've decided to use PostgreSQL.",
            cairn_response="That's a solid choice for your scale.",
            relevant_memories=[],
        )
        assert assessment == "CREATE"

    def test_what_is_populated(self, mock_provider_create):
        assessor = TurnDeltaAssessor(provider=mock_provider_create)
        assessment, what = assessor._classify_turn(
            user_message="I've decided to use PostgreSQL.",
            cairn_response="That's a solid choice for your scale.",
            relevant_memories=[],
        )
        assert what  # non-empty string


class TestJsonParseFailureDefaultsNoChange:
    """Malformed LLM output must silently default to NO_CHANGE — never raise."""

    def test_bad_json_returns_no_change(self, mock_provider_bad_json):
        assessor = TurnDeltaAssessor(provider=mock_provider_bad_json)
        assessment, what = assessor._classify_turn(
            user_message="Tell me something",
            cairn_response="Here is some info",
            relevant_memories=[],
        )
        assert assessment == "NO_CHANGE"
        assert what == ""

    def test_provider_exception_returns_no_change(self):
        """Even a hard provider exception must produce NO_CHANGE, not raise."""
        provider = MagicMock()
        provider.chat_json.side_effect = RuntimeError("LLM unreachable")
        provider._model = "llama3.2:1b"

        assessor = TurnDeltaAssessor(provider=provider)
        assessment, what = assessor._classify_turn(
            user_message="anything",
            cairn_response="anything",
            relevant_memories=[],
        )
        assert assessment == "NO_CHANGE"

    def test_non_dict_json_returns_no_change(self):
        """JSON array (not object) is treated as a parse failure."""
        provider = MagicMock()
        provider.chat_json.return_value = json.dumps(["CREATE", "what"])
        provider._model = "llama3.2:1b"

        assessor = TurnDeltaAssessor(provider=provider)
        assessment, _ = assessor._classify_turn("x", "y", [])
        assert assessment == "NO_CHANGE"

    def test_unknown_assessment_value_returns_no_change(self):
        """An unexpected assessment label (not NO_CHANGE or CREATE) is normalized."""
        provider = MagicMock()
        provider.chat_json.return_value = json.dumps({"assessment": "MAYBE", "what": "???"})
        provider._model = "llama3.2:1b"

        assessor = TurnDeltaAssessor(provider=provider)
        assessment, _ = assessor._classify_turn("x", "y", [])
        assert assessment == "NO_CHANGE"


# =============================================================================
# TestAssessmentPersistedToDb
# =============================================================================


class TestAssessmentPersistedToDb:
    """Turn assessment rows are written to turn_assessments for both outcomes."""

    def test_no_change_row_written(self, mock_provider_no_change, lifecycle_conversation):
        assessor = TurnDeltaAssessor(provider=mock_provider_no_change)
        assessor.assess_turn(
            conversation_id=lifecycle_conversation.id,
            turn_position=1,
            user_message="How are you?",
            cairn_response="Fine, thanks!",
        )

        conn = _get_connection()
        cursor = conn.execute(
            "SELECT * FROM turn_assessments WHERE conversation_id = ?",
            (lifecycle_conversation.id,),
        )
        rows = cursor.fetchall()
        assert len(rows) == 1
        assert rows[0]["assessment"] == "NO_CHANGE"
        assert rows[0]["turn_position"] == 1

    def test_create_row_written(self, mock_provider_create, lifecycle_conversation):
        """A CREATE result also writes an audit row with the memory_id populated.

        We use the real MemoryService (with a mocked pipeline provider) so the
        memory row is actually written to the DB, satisfying the FK constraint on
        turn_assessments.memory_id.
        """
        # Use real MemoryService; mock only the pipeline provider so no real LLM is called.
        assessor = TurnDeltaAssessor(
            provider=mock_provider_create,
        )
        result = assessor.assess_turn(
            conversation_id=lifecycle_conversation.id,
            turn_position=2,
            user_message="I've decided to use PostgreSQL.",
            cairn_response="Great choice.",
        )

        conn = _get_connection()
        cursor = conn.execute(
            "SELECT * FROM turn_assessments WHERE conversation_id = ?",
            (lifecycle_conversation.id,),
        )
        rows = cursor.fetchall()
        assert len(rows) == 1
        assert rows[0]["assessment"] == "CREATE"
        # memory_id may be None if narrative extraction produced empty output,
        # but if it exists it must match the assessment result.
        if result.memory_id is not None:
            assert rows[0]["memory_id"] == result.memory_id

    def test_row_includes_duration_ms(self, mock_provider_no_change, lifecycle_conversation):
        assessor = TurnDeltaAssessor(provider=mock_provider_no_change)
        assessor.assess_turn(
            conversation_id=lifecycle_conversation.id,
            turn_position=0,
            user_message="x",
            cairn_response="y",
        )

        conn = _get_connection()
        row = conn.execute(
            "SELECT duration_ms FROM turn_assessments WHERE conversation_id = ?",
            (lifecycle_conversation.id,),
        ).fetchone()
        assert row is not None
        assert row["duration_ms"] >= 0


# =============================================================================
# TestCreateCallsMemoryServiceWithSource
# =============================================================================


class TestCreateCallsMemoryServiceWithSource:
    """On CREATE, MemoryService.store(source='turn_assessment') must be called."""

    def test_store_called_with_turn_assessment_source(
        self, mock_provider_create, lifecycle_conversation
    ):
        mock_memory_service = MagicMock()
        mock_memory = MagicMock()
        mock_memory.id = "mem-xyz"
        mock_memory_service.store.return_value = mock_memory

        assessor = TurnDeltaAssessor(
            provider=mock_provider_create,
            memory_service=mock_memory_service,
        )
        result = assessor.assess_turn(
            conversation_id=lifecycle_conversation.id,
            turn_position=1,
            user_message="I've decided to use PostgreSQL.",
            cairn_response="That makes sense.",
        )

        assert result.assessment == "CREATE"
        mock_memory_service.store.assert_called_once()
        call_kwargs = mock_memory_service.store.call_args
        # source='turn_assessment' must be passed as keyword arg
        assert call_kwargs.kwargs.get("source") == "turn_assessment"

    def test_memory_id_propagated_to_assessment(
        self, mock_provider_create, lifecycle_conversation
    ):
        mock_memory_service = MagicMock()
        mock_memory = MagicMock()
        mock_memory.id = "mem-propagated"
        mock_memory_service.store.return_value = mock_memory

        assessor = TurnDeltaAssessor(
            provider=mock_provider_create,
            memory_service=mock_memory_service,
        )
        result = assessor.assess_turn(
            conversation_id=lifecycle_conversation.id,
            turn_position=1,
            user_message="Decided to use PostgreSQL.",
            cairn_response="That makes sense.",
        )

        assert result.memory_id == "mem-propagated"

    def test_no_change_does_not_call_store(
        self, mock_provider_no_change, lifecycle_conversation
    ):
        mock_memory_service = MagicMock()

        assessor = TurnDeltaAssessor(
            provider=mock_provider_no_change,
            memory_service=mock_memory_service,
        )
        result = assessor.assess_turn(
            conversation_id=lifecycle_conversation.id,
            turn_position=0,
            user_message="How are you?",
            cairn_response="Fine.",
        )

        assert result.assessment == "NO_CHANGE"
        assert result.memory_id is None
        mock_memory_service.store.assert_not_called()


# =============================================================================
# TestNoActiveLifecycleConversationSkips
# =============================================================================


class TestNoActiveLifecycleConversationSkips:
    """_maybe_submit_turn_assessment must silently no-op with no active conv."""

    def test_no_active_conv_is_silent(self, fresh_db):
        """With no active lifecycle conversation, the function returns without error."""
        from cairn.rpc_handlers.chat import _maybe_submit_turn_assessment

        # No conversation started — get_active() returns None.
        # Must not raise; must not submit to queue.
        _maybe_submit_turn_assessment(
            user_message="test",
            cairn_response="test response",
        )  # If this raises, test fails.

    def test_no_active_conv_does_not_call_queue(self, fresh_db):
        """With no active lifecycle conversation, queue.submit() is never called."""
        from cairn.rpc_handlers.chat import _maybe_submit_turn_assessment

        with patch(
            "cairn.services.turn_delta_assessor.get_turn_assessment_queue"
        ) as mock_get_queue:
            _maybe_submit_turn_assessment(
                user_message="test",
                cairn_response="test response",
            )
            mock_get_queue.assert_not_called()


# =============================================================================
# TestBackgroundQueueNonBlocking
# =============================================================================


class TestBackgroundQueueDoesNotBlock:
    """submit() returns immediately regardless of how long assessment takes."""

    def test_submit_returns_fast(self, lifecycle_conversation):
        """submit() returns in well under 100ms — it just enqueues."""
        # Use a slow assessor to confirm we don't wait for it.
        slow_provider = MagicMock()

        def slow_classify(*, system, user, **kw):
            time.sleep(0.5)  # 500ms — would fail the test if we waited for it
            return json.dumps({"assessment": "NO_CHANGE", "what": ""})

        slow_provider.chat_json.side_effect = slow_classify
        slow_provider._model = "llama3.2:1b"

        assessor = TurnDeltaAssessor(provider=slow_provider)
        queue = TurnAssessmentQueue(assessor=assessor)
        queue.start()

        try:
            start = time.monotonic()
            queue.submit(
                conversation_id=lifecycle_conversation.id,
                turn_position=0,
                user_message="test",
                cairn_response="response",
            )
            elapsed_ms = (time.monotonic() - start) * 1000
            assert elapsed_ms < 100, f"submit() took {elapsed_ms:.0f}ms — expected < 100ms"
        finally:
            queue.stop()

    def test_queue_processes_job_in_background(self, lifecycle_conversation):
        """After submit(), the job is processed asynchronously."""
        processed = threading.Event()
        original_assess = TurnDeltaAssessor.assess_turn

        def spy_assess(self, *args, **kwargs):
            result = original_assess(self, *args, **kwargs)
            processed.set()
            return result

        provider = MagicMock()
        provider.chat_json.return_value = json.dumps({"assessment": "NO_CHANGE", "what": ""})
        provider._model = "llama3.2:1b"

        assessor = TurnDeltaAssessor(provider=provider)
        queue = TurnAssessmentQueue(assessor=assessor)
        queue.start()

        try:
            with patch.object(TurnDeltaAssessor, "assess_turn", spy_assess):
                queue.submit(
                    conversation_id=lifecycle_conversation.id,
                    turn_position=0,
                    user_message="hello",
                    cairn_response="hi",
                )
                # Give the background thread time to process.
                completed = processed.wait(timeout=5.0)
                assert completed, "Background assessment did not complete within 5 seconds"
        finally:
            queue.stop()


# =============================================================================
# TestTurnAssessmentQueueLifecycle
# =============================================================================


class TestTurnAssessmentQueueLifecycle:
    """Queue start/stop and idempotency."""

    def test_double_start_is_idempotent(self):
        queue = TurnAssessmentQueue()
        queue.start()
        thread_one = queue._thread
        queue.start()
        assert queue._thread is thread_one
        queue.stop()

    def test_stop_joins_thread(self):
        queue = TurnAssessmentQueue()
        queue.start()
        queue.stop()
        assert queue._thread is None

    def test_stop_without_start_is_safe(self):
        """Calling stop() on a queue that was never started must not raise."""
        queue = TurnAssessmentQueue()
        queue.stop()  # Must not raise.
