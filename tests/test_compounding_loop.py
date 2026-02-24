"""Integration tests for Phase 5: Compounding Loop.

Covers:
- Correction chains (correct → supersede) and signal_count inheritance
- Supersession chain traversal via get_latest_version()
- Thread resolution (memory_state_deltas)
- Open thread queries
- Search excluding superseded memories
- Multi-conversation memory flows
- Recency decay integration
"""

from __future__ import annotations

import json
import os
import struct
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from reos.play_db import (
    _get_connection,
    _transaction,
    close_connection,
    init_db,
)
from reos.services.memory_service import MemoryError, MemoryService

# =============================================================================
# Helpers
# =============================================================================


def _make_embedding(value: float = 0.5) -> bytes:
    """Create a fake 384-dim embedding."""
    return struct.pack("f" * 384, *([value] * 384))


def _mock_provider(*, is_match: bool = False, merged: str = "") -> MagicMock:
    """Mock OllamaProvider that returns a controlled dedup judgment."""
    provider = MagicMock()
    provider.chat_json.return_value = json.dumps({
        "is_match": is_match,
        "reason": "test",
        "merged_narrative": merged if is_match else "",
    })
    return provider


def _mock_embedding_service(
    similar_results: list | None = None,
    embed_value: float = 0.5,
) -> MagicMock:
    """Mock EmbeddingService with no similar results by default."""
    svc = MagicMock()
    svc.embed.return_value = _make_embedding(embed_value)
    svc.find_similar.return_value = similar_results or []
    svc.is_available = True
    return svc


def _make_service(
    *,
    is_match: bool = False,
    merged: str = "",
    similar_results: list | None = None,
) -> MemoryService:
    """Convenience factory: MemoryService with mocked provider and embedding."""
    return MemoryService(
        provider=_mock_provider(is_match=is_match, merged=merged),
        embedding_service=_mock_embedding_service(similar_results=similar_results),
        graph_store=MagicMock(),
    )


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture()
def mem_db(tmp_path):
    """Fresh isolated database for each test."""
    os.environ["REOS_DATA_DIR"] = str(tmp_path)
    init_db()
    yield tmp_path
    close_connection()
    os.environ.pop("REOS_DATA_DIR", None)


@pytest.fixture()
def conversation_id(mem_db):
    """Create a conversation and return its ID."""
    from reos.services.conversation_service import ConversationService

    service = ConversationService()
    conv = service.start()
    service.add_message(conv.id, "user", "Let's discuss architecture.")
    return conv.id


@pytest.fixture()
def second_conversation_id(mem_db, conversation_id):
    """Create a second conversation (singleton: close first one first)."""
    from reos.services.conversation_service import ConversationService

    # Archive the first conversation to satisfy the singleton constraint
    with _transaction() as conn:
        conn.execute(
            "UPDATE conversations SET status = 'archived' WHERE id = ?",
            (conversation_id,),
        )

    svc = ConversationService()
    conv = svc.start()
    svc.add_message(conv.id, "user", "Second conversation, same topic.")
    return conv.id


# =============================================================================
# TestCorrectionChain
# =============================================================================


class TestCorrectionChain:
    """Correction creates a new memory, supersedes the old one, and inherits signals."""

    def test_correct_creates_new_and_supersedes_old(self, mem_db, conversation_id):
        """correct() creates a new memory and marks the old one as superseded."""
        svc = _make_service()

        original = svc.store(conversation_id, "Alex prefers email.")
        corrected = svc.correct(
            original.id,
            "Alex actually prefers Slack.",
            conversation_id,
        )

        # New memory has the corrected narrative
        assert corrected.narrative == "Alex actually prefers Slack."
        assert corrected.id != original.id

        # Original is now superseded
        old = svc.get_by_id(original.id)
        assert old is not None
        assert old.status == "superseded"

    def test_corrected_memory_inherits_signal_count(self, mem_db, conversation_id):
        """New memory's signal_count = old memory's signal_count + its own (1)."""
        svc = _make_service()

        # Store original and give it signal_count=3 manually
        original = svc.store(conversation_id, "Old fact.")
        with _transaction() as conn:
            conn.execute(
                "UPDATE memories SET signal_count = 3 WHERE id = ?",
                (original.id,),
            )

        corrected = svc.correct(
            original.id,
            "Corrected fact.",
            conversation_id,
        )

        # Inherited 3 from old + started at 1 = 4
        corrected_fresh = svc.get_by_id(corrected.id)
        assert corrected_fresh is not None
        assert corrected_fresh.signal_count == 4

    def test_correction_chain_two_deep(self, mem_db, conversation_id):
        """Correct A→B, then correct B→C. A and B are superseded; C accumulates signals."""
        svc = _make_service()

        mem_a = svc.store(conversation_id, "Memory A.")
        mem_b = svc.correct(mem_a.id, "Memory B.", conversation_id)
        mem_c = svc.correct(mem_b.id, "Memory C.", conversation_id)

        # A and B superseded
        assert svc.get_by_id(mem_a.id).status == "superseded"
        assert svc.get_by_id(mem_b.id).status == "superseded"

        # C is live
        c_fresh = svc.get_by_id(mem_c.id)
        assert c_fresh is not None
        assert c_fresh.status == "pending_review"

        # Signal accumulation: A=1 → B=1+1=2 → C=1+2=3
        assert c_fresh.signal_count == 3


# =============================================================================
# TestSupersessionChain
# =============================================================================


def _make_service_with_real_graph(
    *,
    is_match: bool = False,
    merged: str = "",
    similar_results: list | None = None,
) -> MemoryService:
    """MemoryService with a real MemoryGraphStore so SUPERSEDES edges are persisted."""
    from reos.memory.graph_store import MemoryGraphStore

    return MemoryService(
        provider=_mock_provider(is_match=is_match, merged=merged),
        embedding_service=_mock_embedding_service(similar_results=similar_results),
        graph_store=MemoryGraphStore(),
    )


class TestSupersessionChain:
    """get_latest_version() follows the SUPERSEDES chain to find the current memory."""

    def test_get_latest_version_no_supersession(self, mem_db, conversation_id):
        """Non-superseded memory returns itself."""
        svc = _make_service_with_real_graph()
        mem = svc.store(conversation_id, "Stable memory.")

        latest = svc.get_latest_version(mem.id)
        assert latest is not None
        assert latest.id == mem.id

    def test_get_latest_version_one_hop(self, mem_db, conversation_id):
        """Superseded memory returns its direct successor."""
        svc = _make_service_with_real_graph()
        old = svc.store(conversation_id, "Old version.")
        new = svc.store(conversation_id, "New version.")

        svc.supersede(old.id, new.id)

        latest = svc.get_latest_version(old.id)
        assert latest is not None
        assert latest.id == new.id

    def test_get_latest_version_multi_hop(self, mem_db, conversation_id):
        """A superseded by B superseded by C → get_latest_version(A) returns C."""
        svc = _make_service_with_real_graph()
        mem_a = svc.store(conversation_id, "Version A.")
        mem_b = svc.store(conversation_id, "Version B.")
        mem_c = svc.store(conversation_id, "Version C.")

        svc.supersede(mem_a.id, mem_b.id)
        svc.supersede(mem_b.id, mem_c.id)

        latest = svc.get_latest_version(mem_a.id)
        assert latest is not None
        assert latest.id == mem_c.id

    def test_get_latest_version_not_found(self, mem_db):
        """Nonexistent memory ID returns None."""
        svc = _make_service()
        assert svc.get_latest_version("nonexistent-id") is None


# =============================================================================
# TestResolveThread
# =============================================================================


def _insert_delta(memory_id: str, delta_type: str = "waiting_on", detail: str = "details") -> str:
    """Insert a memory_state_delta row and return its ID."""
    delta_id = uuid4().hex[:12]
    with _transaction() as conn:
        conn.execute(
            """INSERT INTO memory_state_deltas (id, memory_id, delta_type, delta_data)
               VALUES (?, ?, ?, ?)""",
            (delta_id, memory_id, delta_type, json.dumps({"detail": detail})),
        )
    return delta_id


class TestResolveThread:
    """resolve_thread() marks a state delta as applied."""

    def test_resolve_thread_marks_applied(self, mem_db, conversation_id):
        """resolve_thread sets applied=1 and applied_at on the delta row."""
        svc = _make_service()
        mem = svc.store(conversation_id, "Waiting on Alex.")
        delta_id = _insert_delta(mem.id)

        result = svc.resolve_thread(mem.id, delta_id)

        assert result["applied"] is True
        assert result["applied_at"] is not None

        # Verify persisted in DB
        conn = _get_connection()
        row = conn.execute(
            "SELECT applied, applied_at FROM memory_state_deltas WHERE id = ?",
            (delta_id,),
        ).fetchone()
        assert row["applied"] == 1
        assert row["applied_at"] is not None

    def test_resolve_thread_with_note(self, mem_db, conversation_id):
        """Resolution note is stored in delta_data."""
        svc = _make_service()
        mem = svc.store(conversation_id, "Question outstanding.")
        delta_id = _insert_delta(mem.id, delta_type="question_opened")

        result = svc.resolve_thread(mem.id, delta_id, resolution_note="Answered by Alex.")

        assert result["delta_data"]["resolution_note"] == "Answered by Alex."
        assert result["delta_data"].get("resolved") is True

    def test_resolve_thread_already_resolved_raises(self, mem_db, conversation_id):
        """Resolving an already-resolved delta raises MemoryError."""
        svc = _make_service()
        mem = svc.store(conversation_id, "Done item.")
        delta_id = _insert_delta(mem.id)

        svc.resolve_thread(mem.id, delta_id)

        with pytest.raises(MemoryError, match="already resolved"):
            svc.resolve_thread(mem.id, delta_id)

    def test_resolve_thread_missing_delta_raises(self, mem_db, conversation_id):
        """Nonexistent delta_id raises MemoryError."""
        svc = _make_service()
        mem = svc.store(conversation_id, "Some memory.")

        with pytest.raises(MemoryError, match="not found"):
            svc.resolve_thread(mem.id, "bogus-delta-id")


# =============================================================================
# TestGetOpenThreads
# =============================================================================


class TestGetOpenThreads:
    """get_open_threads() returns only unresolved deltas."""

    def test_returns_only_unresolved(self, mem_db, conversation_id):
        """Creates 2 deltas, resolves 1; only the unresolved one surfaces."""
        svc = _make_service()
        mem = svc.store(conversation_id, "Memory with threads.")
        delta_a = _insert_delta(mem.id, detail="thread A")
        delta_b = _insert_delta(mem.id, detail="thread B")

        svc.resolve_thread(mem.id, delta_a)

        open_threads = svc.get_open_threads()
        open_ids = [t["id"] for t in open_threads]

        assert delta_a not in open_ids
        assert delta_b in open_ids

    def test_empty_when_all_resolved(self, mem_db, conversation_id):
        """When all deltas are resolved get_open_threads returns an empty list."""
        svc = _make_service()
        mem = svc.store(conversation_id, "All done memory.")
        delta_a = _insert_delta(mem.id, detail="thread A")
        delta_b = _insert_delta(mem.id, detail="thread B")

        svc.resolve_thread(mem.id, delta_a)
        svc.resolve_thread(mem.id, delta_b)

        assert svc.get_open_threads() == []


# =============================================================================
# TestSearchExcludesSuperseded
# =============================================================================


class TestSearchExcludesSuperseded:
    """search() must not return memories with status='superseded'."""

    def test_search_excludes_superseded_memories(self, mem_db, conversation_id):
        """After supersession the old memory does not appear in search results.

        The SQL in search() filters WHERE status != 'superseded', so the old
        memory's block_id is never passed to find_similar. We simulate this by
        having find_similar return only new.id (because old.id is not a candidate).
        """
        embedding = _make_embedding(0.5)
        embedding_service = _mock_embedding_service()

        svc = MemoryService(
            provider=_mock_provider(is_match=False),
            embedding_service=embedding_service,
            graph_store=MagicMock(),
        )

        old = svc.store(conversation_id, "Old understanding of the problem.", embedding=embedding)
        new = svc.store(conversation_id, "New understanding of the problem.", embedding=embedding)

        svc.approve(old.id)
        svc.approve(new.id)
        svc.supersede(old.id, new.id)

        # Verify old is now superseded in DB
        old_db = svc.get_by_id(old.id)
        assert old_db.status == "superseded"

        # The search SQL excludes superseded rows from candidates, so find_similar
        # only receives new.id's embedding. Mock accordingly.
        embedding_service.find_similar.return_value = [(new.id, 0.93)]
        embedding_service.embed.return_value = embedding

        results = svc.search("understanding of the problem")
        result_ids = [m.id for m, _ in results]

        assert old.id not in result_ids
        assert new.id in result_ids


# =============================================================================
# TestMultiConversationFlow
# =============================================================================


class TestMultiConversationFlow:
    """Memories persist across conversation boundaries."""

    def test_memory_across_conversations(
        self, mem_db, conversation_id, second_conversation_id
    ):
        """Memories created in conv1 are accessible after starting conv2."""
        svc = _make_service()

        mem = svc.store(conversation_id, "Architecture decision from conv1.")

        # Retrieve from the second conversation context (no conv filter)
        fetched = svc.get_by_id(mem.id)
        assert fetched is not None
        assert fetched.narrative == "Architecture decision from conv1."

        # Create a memory in conv2 and verify both coexist
        mem2 = svc.store(second_conversation_id, "Follow-up from conv2.")
        all_memories = svc.list_memories()
        all_ids = [m.id for m in all_memories]

        assert mem.id in all_ids
        assert mem2.id in all_ids

    def test_signal_strengthening_across_conversations(
        self, mem_db, conversation_id, second_conversation_id
    ):
        """Same insight in conv2 reinforces a memory from conv1 (is_match=True)."""
        embedding = _make_embedding(0.5)
        embedding_service = _mock_embedding_service()

        # Store original memory in conv1
        svc_conv1 = MemoryService(
            provider=_mock_provider(is_match=False),
            embedding_service=embedding_service,
            graph_store=MagicMock(),
        )
        original = svc_conv1.store(
            conversation_id,
            "SQLite is the right choice for local-first.",
            embedding=embedding,
        )
        assert original.signal_count == 1

        # Second conversation: same insight → should reinforce
        embedding_service.find_similar.return_value = [(original.id, 0.95)]
        svc_conv2 = MemoryService(
            provider=_mock_provider(
                is_match=True,
                merged="SQLite is definitively the right choice for local-first apps.",
            ),
            embedding_service=embedding_service,
            graph_store=MagicMock(),
        )
        reinforced = svc_conv2.store(
            second_conversation_id,
            "We still think SQLite is right for local-first.",
            embedding=_make_embedding(0.51),
        )

        # The reinforced result should be the original memory with incremented count
        assert reinforced.id == original.id
        assert reinforced.signal_count == 2


# =============================================================================
# TestRecencyDecayIntegration
# =============================================================================


class TestRecencyDecayIntegration:
    """Recency weight decays over time — older memories score lower."""

    def test_older_memories_scored_lower(self, mem_db):
        """A memory created 60 days ago has lower recency weight than one created now."""
        from reos.memory.retriever import _compute_recency_weight

        now_iso = datetime.now(UTC).isoformat()
        old_iso = (datetime.now(UTC) - timedelta(days=60)).isoformat()

        weight_now = _compute_recency_weight(now_iso)
        weight_old = _compute_recency_weight(old_iso)

        assert weight_now > weight_old
        # 60 days = 2 × half-life (30 days) → weight ≈ 0.25
        assert weight_old < 0.5

    def test_recency_weight_is_one_for_current_timestamp(self, mem_db):
        """A memory with timestamp 'now' has recency weight very close to 1.0."""
        from reos.memory.retriever import _compute_recency_weight

        now_iso = datetime.now(UTC).isoformat()
        weight = _compute_recency_weight(now_iso)
        assert weight > 0.99

    def test_recency_weight_invalid_date_returns_default(self, mem_db):
        """Unparseable date returns the default fallback (0.5)."""
        from reos.memory.retriever import _compute_recency_weight

        weight = _compute_recency_weight("not-a-date")
        assert weight == 0.5
