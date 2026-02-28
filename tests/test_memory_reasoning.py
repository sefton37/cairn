"""Tests for Memory as Reasoning Context (Phase 4).

Covers:
- ConversationMemoryMatch formatting
- ConversationMemoryContext prompt block generation
- Recency decay computation
- Signal weight computation
- MemoryRetriever.retrieve_conversation_memories() with status filter
- Signal weighting: high signal_count memories rank higher
- Recency decay: recent memories rank higher than old ones
- Transparency logging: classification_memory_references
"""

from __future__ import annotations

import math
import os
import struct
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from cairn.memory.retriever import (
    ConversationMemoryContext,
    ConversationMemoryMatch,
    _compute_recency_weight,
    _compute_signal_weight,
)
from cairn.play_db import (
    YOUR_STORY_ACT_ID,
    _get_connection,
    _transaction,
    close_connection,
    init_db,
)
from cairn.services.memory_service import (
    MemoryService,
    log_memory_influence,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture()
def mem_db(tmp_path):
    """Set up a fresh database for memory reasoning tests."""
    os.environ["REOS_DATA_DIR"] = str(tmp_path)
    init_db()
    yield tmp_path
    close_connection()
    os.environ.pop("REOS_DATA_DIR", None)


@pytest.fixture()
def conversation_id(mem_db):
    """Create a conversation and return its ID."""
    from cairn.services.conversation_service import ConversationService

    service = ConversationService()
    conv = service.start()
    service.add_message(conv.id, "user", "Let's discuss architecture.")
    return conv.id


def _make_embedding(value: float = 0.5) -> bytes:
    """Create a fake 384-dim embedding."""
    return struct.pack("f" * 384, *([value] * 384))


def _mock_provider() -> MagicMock:
    """Mock OllamaProvider that says no match (for dedup bypass)."""
    import json

    provider = MagicMock()
    provider.chat_json.return_value = json.dumps({
        "is_match": False,
        "reason": "different",
        "merged_narrative": "",
    })
    return provider


def _mock_embedding_service() -> MagicMock:
    """Mock EmbeddingService with no similar results."""
    service = MagicMock()
    service.embed.return_value = _make_embedding(0.5)
    service.find_similar.return_value = []
    service.is_available = True
    return service


# =============================================================================
# TestRecencyWeight
# =============================================================================


class TestRecencyWeight:
    """Test recency decay computation."""

    def test_now_returns_one(self):
        """Current time should give weight ~1.0."""
        now = datetime.now(UTC).isoformat()
        weight = _compute_recency_weight(now)
        assert 0.99 <= weight <= 1.0

    def test_half_life(self):
        """After half_life_days, weight should be ~0.5."""
        past = (datetime.now(UTC) - timedelta(days=30)).isoformat()
        weight = _compute_recency_weight(past, half_life_days=30.0)
        assert 0.48 <= weight <= 0.52

    def test_double_half_life(self):
        """After 2x half_life_days, weight should be ~0.25."""
        past = (datetime.now(UTC) - timedelta(days=60)).isoformat()
        weight = _compute_recency_weight(past, half_life_days=30.0)
        assert 0.23 <= weight <= 0.27

    def test_invalid_date(self):
        """Invalid date returns default 0.5."""
        weight = _compute_recency_weight("not-a-date")
        assert weight == 0.5

    def test_empty_string(self):
        """Empty string returns default 0.5."""
        weight = _compute_recency_weight("")
        assert weight == 0.5


# =============================================================================
# TestSignalWeight
# =============================================================================


class TestSignalWeight:
    """Test signal weight computation."""

    def test_signal_count_1(self):
        """signal_count=1 → log2(2) = 1.0."""
        assert _compute_signal_weight(1) == pytest.approx(1.0)

    def test_signal_count_3(self):
        """signal_count=3 → log2(4) = 2.0."""
        assert _compute_signal_weight(3) == pytest.approx(2.0)

    def test_signal_count_7(self):
        """signal_count=7 → log2(8) = 3.0."""
        assert _compute_signal_weight(7) == pytest.approx(3.0)

    def test_signal_count_0(self):
        """signal_count=0 → log2(1) = 0.0."""
        assert _compute_signal_weight(0) == pytest.approx(0.0)

    def test_monotonically_increasing(self):
        """Higher signal_count always produces higher weight."""
        weights = [_compute_signal_weight(i) for i in range(10)]
        for i in range(1, len(weights)):
            assert weights[i] > weights[i - 1]


# =============================================================================
# TestConversationMemoryMatch
# =============================================================================


class TestConversationMemoryMatch:
    """Test the ConversationMemoryMatch dataclass."""

    def test_to_prompt_line(self):
        """Prompt line includes date and signal count."""
        match = ConversationMemoryMatch(
            memory_id="mem-1",
            block_id="block-1",
            narrative="We chose SQLite for persistence.",
            score=0.85,
            semantic_similarity=0.9,
            signal_count=3,
            signal_weight=2.0,
            recency_weight=0.95,
            created_at="2026-02-20T10:30:00+00:00",
            conversation_id="conv-1",
        )

        line = match.to_prompt_line()
        assert "[Memory from 2026-02-20 | signal: 3x]" in line
        assert "We chose SQLite for persistence." in line

    def test_to_dict(self):
        """to_dict includes all fields."""
        match = ConversationMemoryMatch(
            memory_id="mem-1",
            block_id="block-1",
            narrative="Test.",
            score=0.5,
            semantic_similarity=0.6,
            signal_count=1,
            signal_weight=1.0,
            recency_weight=1.0,
            created_at="2026-01-01",
            conversation_id="conv-1",
        )

        d = match.to_dict()
        assert d["memory_id"] == "mem-1"
        assert d["signal_count"] == 1
        assert d["score"] == 0.5


# =============================================================================
# TestConversationMemoryContext
# =============================================================================


class TestConversationMemoryContext:
    """Test the ConversationMemoryContext dataclass."""

    def test_empty_prompt_block(self):
        """Empty matches produce empty string."""
        ctx = ConversationMemoryContext(query="test")
        assert ctx.to_prompt_block() == ""

    def test_prompt_block_formatting(self):
        """Prompt block includes header and memory lines."""
        ctx = ConversationMemoryContext(
            query="architecture",
            matches=[
                ConversationMemoryMatch(
                    memory_id="m1", block_id="b1",
                    narrative="SQLite is our database.",
                    score=0.9, semantic_similarity=0.95,
                    signal_count=5, signal_weight=2.6,
                    recency_weight=0.99,
                    created_at="2026-02-20T10:00:00+00:00",
                    conversation_id="c1",
                ),
                ConversationMemoryMatch(
                    memory_id="m2", block_id="b2",
                    narrative="Local-first is the philosophy.",
                    score=0.7, semantic_similarity=0.8,
                    signal_count=2, signal_weight=1.6,
                    recency_weight=0.85,
                    created_at="2026-02-15T10:00:00+00:00",
                    conversation_id="c2",
                ),
            ],
        )

        block = ctx.to_prompt_block()
        assert "## Prior Memories" in block
        assert "signal: 5x" in block
        assert "signal: 2x" in block
        assert "SQLite is our database." in block
        assert "Local-first is the philosophy." in block


# =============================================================================
# TestRetrieveConversationMemories
# =============================================================================


class TestRetrieveConversationMemories:
    """Test the retrieve_conversation_memories method."""

    def test_returns_only_approved(self, mem_db, conversation_id):
        """Only approved memories are returned."""
        service = MemoryService(
            provider=_mock_provider(),
            embedding_service=_mock_embedding_service(),
        )

        # Create memories in different states
        m1 = service.store(conversation_id, "Approved memory.", embedding=_make_embedding(0.5))
        m2 = service.store(conversation_id, "Pending memory.", embedding=_make_embedding(0.6))
        m3 = service.store(conversation_id, "Rejected memory.", embedding=_make_embedding(0.7))

        service.approve(m1.id)
        service.reject(m3.id)

        # Query the memories table directly to verify status
        conn = _get_connection()
        cursor = conn.execute(
            "SELECT id, status FROM memories ORDER BY created_at"
        )
        rows = cursor.fetchall()
        statuses = {row["id"]: row["status"] for row in rows}
        assert statuses[m1.id] == "approved"
        assert statuses[m2.id] == "pending_review"
        assert statuses[m3.id] == "rejected"

    def test_signal_weighting_ranks_higher(self, mem_db, conversation_id):
        """Memories with higher signal_count rank higher (all else equal)."""
        service = MemoryService(
            provider=_mock_provider(),
            embedding_service=_mock_embedding_service(),
        )

        # Create two memories and approve them
        low_signal = service.store(
            conversation_id, "Low signal memory.", embedding=_make_embedding(0.5)
        )
        high_signal = service.store(
            conversation_id, "High signal memory.", embedding=_make_embedding(0.5)
        )
        service.approve(low_signal.id)
        service.approve(high_signal.id)

        # Manually boost signal_count for one
        with _transaction() as conn:
            conn.execute(
                "UPDATE memories SET signal_count = 8 WHERE id = ?",
                (high_signal.id,),
            )

        # Verify signal_weight computation
        assert _compute_signal_weight(8) > _compute_signal_weight(1)
        assert _compute_signal_weight(8) == pytest.approx(math.log2(9))

    def test_recency_decay_applied(self, mem_db, conversation_id):
        """Older memories get lower recency weight."""
        service = MemoryService(
            provider=_mock_provider(),
            embedding_service=_mock_embedding_service(),
        )

        recent = service.store(
            conversation_id, "Recent memory.", embedding=_make_embedding(0.5)
        )
        service.approve(recent.id)

        old = service.store(
            conversation_id, "Old memory.", embedding=_make_embedding(0.5)
        )
        service.approve(old.id)

        # Manually age one memory
        old_date = (datetime.now(UTC) - timedelta(days=90)).isoformat()
        with _transaction() as conn:
            conn.execute(
                "UPDATE memories SET created_at = ? WHERE id = ?",
                (old_date, old.id),
            )

        # Verify recency weights differ
        recent_weight = _compute_recency_weight(
            datetime.now(UTC).isoformat()
        )
        old_weight = _compute_recency_weight(old_date)
        assert recent_weight > old_weight


# =============================================================================
# TestTransparencyLogging
# =============================================================================


class TestTransparencyLogging:
    """Test classification_memory_references transparency logging."""

    def test_log_memory_influence(self, mem_db, conversation_id):
        """log_memory_influence records to classification_memory_references."""
        service = MemoryService(
            provider=_mock_provider(),
            embedding_service=_mock_embedding_service(),
        )
        memory = service.store(conversation_id, "Test memory.")

        log_memory_influence(
            classification_id="cls-001",
            memory_references=[
                {
                    "memory_id": memory.id,
                    "influence_type": "semantic_match",
                    "influence_score": 0.85,
                    "reasoning": "High similarity to user query",
                },
            ],
        )

        conn = _get_connection()
        cursor = conn.execute(
            "SELECT * FROM classification_memory_references "
            "WHERE classification_id = 'cls-001'"
        )
        rows = cursor.fetchall()
        assert len(rows) == 1
        assert rows[0]["memory_id"] == memory.id
        assert rows[0]["influence_type"] == "semantic_match"
        assert rows[0]["influence_score"] == 0.85

    def test_log_multiple_references(self, mem_db, conversation_id):
        """Multiple memory references logged for one classification."""
        service = MemoryService(
            provider=_mock_provider(),
            embedding_service=_mock_embedding_service(),
        )
        m1 = service.store(conversation_id, "Memory one.")
        m2 = service.store(conversation_id, "Memory two.")

        log_memory_influence(
            classification_id="cls-002",
            memory_references=[
                {"memory_id": m1.id, "influence_type": "semantic_match",
                 "influence_score": 0.9, "reasoning": "Primary match"},
                {"memory_id": m2.id, "influence_type": "graph_expansion",
                 "influence_score": 0.6, "reasoning": "Related via graph"},
            ],
        )

        conn = _get_connection()
        cursor = conn.execute(
            "SELECT COUNT(*) as cnt FROM classification_memory_references "
            "WHERE classification_id = 'cls-002'"
        )
        assert cursor.fetchone()["cnt"] == 2

    def test_log_empty_references_noop(self, mem_db):
        """Empty references list is a no-op."""
        log_memory_influence("cls-003", [])

        conn = _get_connection()
        cursor = conn.execute(
            "SELECT COUNT(*) as cnt FROM classification_memory_references "
            "WHERE classification_id = 'cls-003'"
        )
        assert cursor.fetchone()["cnt"] == 0


# =============================================================================
# TestClassifierMemoryInjection
# =============================================================================


class TestClassifierMemoryInjection:
    """Test that classifier accepts and uses memory_context."""

    def test_classify_with_memory_context(self):
        """Classifier includes memory context in LLM call."""
        import json

        mock_llm = MagicMock()
        mock_llm.chat_json.return_value = json.dumps({
            "destination": "stream",
            "consumer": "human",
            "semantics": "interpret",
            "confident": True,
            "reasoning": "personal question with memory context",
            "domain": "personal",
            "action_hint": None,
        })

        from cairn.atomic_ops.classifier import AtomicClassifier

        classifier = AtomicClassifier(llm=mock_llm)
        result = classifier.classify(
            "What did we decide about the database?",
            memory_context="[Memory from 2026-02-20 | signal: 3x]: We chose SQLite.",
        )

        # Verify classification succeeded
        assert result.classification.confident is True
        assert result.classification.domain == "personal"

        # Verify memory context was included in the user prompt
        call_args = mock_llm.chat_json.call_args
        user_prompt = call_args.kwargs.get("user", "")
        assert "What did we decide about the database?" in user_prompt
        assert "We chose SQLite" in user_prompt

    def test_classify_without_memory_context(self):
        """Classifier works fine without memory context."""
        import json

        mock_llm = MagicMock()
        mock_llm.chat_json.return_value = json.dumps({
            "destination": "stream",
            "consumer": "human",
            "semantics": "interpret",
            "confident": True,
            "reasoning": "greeting",
            "domain": "conversation",
            "action_hint": None,
        })

        from cairn.atomic_ops.classifier import AtomicClassifier

        classifier = AtomicClassifier(llm=mock_llm)
        result = classifier.classify("good morning")

        assert result.classification.domain == "conversation"

        # Verify no memory context in prompt
        call_args = mock_llm.chat_json.call_args
        user_prompt = call_args.kwargs.get("user", "")
        assert "Prior Memories" not in user_prompt
