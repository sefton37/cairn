"""Tests for MemoryService — storage, deduplication, routing, review gate.

Covers:
- Memory creation (store without duplicates)
- Deduplication / signal strengthening
- Review gate state machine (pending_review → approved/rejected)
- Routing to Acts
- Correction / supersession
- Narrative editing
- Querying and listing
"""

from __future__ import annotations

import json
import os
import struct
from unittest.mock import MagicMock, patch

import pytest

from reos.play_db import (
    YOUR_STORY_ACT_ID,
    _get_connection,
    _transaction,
    close_connection,
    init_db,
)
from reos.services.memory_service import (
    DeduplicationResult,
    Memory,
    MemoryError,
    MemoryService,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture()
def mem_db(tmp_path):
    """Set up a fresh database for memory tests."""
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
    service.add_message(conv.id, "user", "Hello, let's talk about SQLite.")
    service.add_message(conv.id, "cairn", "Sure! SQLite is great for local-first apps.")
    return conv.id


@pytest.fixture()
def second_conversation_id(mem_db):
    """Create a second conversation (after closing first) and return its ID."""
    from reos.services.conversation_service import ConversationService

    service = ConversationService()
    # Close any active conversation first
    active = service.get_active()
    if active:
        service.close(active.id)
        # Manually archive to clear the way
        service.start_compression(active.id)
        service._transition(active.id, "archived")

    conv = service.start()
    service.add_message(conv.id, "user", "Another conversation about databases.")
    return conv.id


def _make_embedding(value: float = 0.5) -> bytes:
    """Create a fake 384-dim embedding."""
    return struct.pack("f" * 384, *([value] * 384))


def _mock_provider(is_match: bool = False, merged: str = "") -> MagicMock:
    """Create a mock OllamaProvider for dedup judgment."""
    provider = MagicMock()
    provider.chat_json.return_value = json.dumps({
        "is_match": is_match,
        "reason": "test reason",
        "merged_narrative": merged,
    })
    return provider


def _mock_embedding_service(similar_results: list | None = None) -> MagicMock:
    """Create a mock EmbeddingService."""
    service = MagicMock()
    service.embed.return_value = _make_embedding(0.5)
    service.find_similar.return_value = similar_results or []
    return service


# =============================================================================
# TestMemoryCreation
# =============================================================================


class TestMemoryCreation:
    """Test basic memory creation without dedup."""

    def test_store_creates_memory(self, mem_db, conversation_id):
        """Store creates a new memory in pending_review status."""
        embedding_service = _mock_embedding_service()
        service = MemoryService(
            provider=_mock_provider(),
            embedding_service=embedding_service,
        )

        memory = service.store(
            conversation_id,
            "We decided to use SQLite for the project.",
            model="qwen2.5:1.5b",
            confidence=0.85,
        )

        assert memory.id
        assert memory.narrative == "We decided to use SQLite for the project."
        assert memory.status == "pending_review"
        assert memory.signal_count == 1
        assert memory.is_your_story is True
        assert memory.extraction_model == "qwen2.5:1.5b"
        assert memory.extraction_confidence == 0.85

    def test_store_creates_block(self, mem_db, conversation_id):
        """Store creates a block in the blocks table."""
        service = MemoryService(
            provider=_mock_provider(),
            embedding_service=_mock_embedding_service(),
        )

        memory = service.store(conversation_id, "Test narrative.")

        conn = _get_connection()
        cursor = conn.execute(
            "SELECT * FROM blocks WHERE id = ?", (memory.block_id,)
        )
        block = cursor.fetchone()
        assert block is not None
        assert block["type"] == "memory"
        assert block["act_id"] == YOUR_STORY_ACT_ID

    def test_store_with_embedding(self, mem_db, conversation_id):
        """Store saves embedding in block_embeddings table."""
        embedding = _make_embedding(0.7)
        service = MemoryService(
            provider=_mock_provider(),
            embedding_service=_mock_embedding_service(),
        )

        memory = service.store(
            conversation_id,
            "Test narrative with embedding.",
            embedding=embedding,
        )

        conn = _get_connection()
        cursor = conn.execute(
            "SELECT * FROM block_embeddings WHERE block_id = ?",
            (memory.block_id,),
        )
        row = cursor.fetchone()
        assert row is not None
        assert row["embedding"] == embedding

    def test_store_with_destination_act(self, mem_db, conversation_id):
        """Store routes to a specific Act when destination provided."""
        # Create a block to act as the destination (destination_act_id refs blocks)
        with _transaction() as c:
            c.execute(
                """INSERT INTO acts (act_id, title, active, position, created_at, updated_at)
                   VALUES ('act-career', 'Career', 1, 0, '2024-01-01', '2024-01-01')"""
            )

        service = MemoryService(
            provider=_mock_provider(),
            embedding_service=_mock_embedding_service(),
        )

        # Use the act_id as destination — the block act_id will point here
        memory = service.store(
            conversation_id,
            "Career-related memory.",
            destination_act_id="act-career",
        )

        assert memory.destination_act_id == "act-career"
        assert memory.is_your_story is False

    def test_get_by_id(self, mem_db, conversation_id):
        """Retrieve a memory by ID."""
        service = MemoryService(
            provider=_mock_provider(),
            embedding_service=_mock_embedding_service(),
        )
        memory = service.store(conversation_id, "Retrievable memory.")

        fetched = service.get_by_id(memory.id)
        assert fetched is not None
        assert fetched.narrative == "Retrievable memory."

    def test_get_by_id_not_found(self, mem_db):
        """Returns None for nonexistent memory."""
        service = MemoryService(
            provider=_mock_provider(),
            embedding_service=_mock_embedding_service(),
        )
        assert service.get_by_id("nonexistent") is None

    def test_get_by_conversation(self, mem_db, conversation_id):
        """Get all memories for a conversation."""
        service = MemoryService(
            provider=_mock_provider(),
            embedding_service=_mock_embedding_service(),
        )
        service.store(conversation_id, "Memory one.")
        service.store(conversation_id, "Memory two.")

        memories = service.get_by_conversation(conversation_id)
        assert len(memories) == 2


# =============================================================================
# TestDeduplication
# =============================================================================


class TestDeduplication:
    """Test signal strengthening / dedup logic."""

    def test_no_duplicate_when_no_similar(self, mem_db, conversation_id):
        """New memory created when no similar memories exist."""
        service = MemoryService(
            provider=_mock_provider(is_match=False),
            embedding_service=_mock_embedding_service(similar_results=[]),
        )

        memory = service.store(conversation_id, "Unique insight about testing.")
        assert memory.signal_count == 1

    def test_reinforces_when_duplicate_found(self, mem_db, conversation_id):
        """Signal count incremented when LLM judges match."""
        embedding_service = _mock_embedding_service()
        # First store: no duplicates
        service = MemoryService(
            provider=_mock_provider(is_match=False),
            embedding_service=embedding_service,
        )
        first = service.store(
            conversation_id,
            "SQLite is the best choice for local-first apps.",
            embedding=_make_embedding(0.5),
        )
        assert first.signal_count == 1

        # Now mock the find_similar to return the first memory
        embedding_service.find_similar.return_value = [
            (first.id, 0.92),
        ]

        # Provider judges it as a match
        match_provider = _mock_provider(
            is_match=True,
            merged="SQLite remains the best choice for local-first applications.",
        )
        service._provider = match_provider

        # Store a "duplicate"
        second = service.store(
            conversation_id,
            "We confirmed SQLite is ideal for local-first.",
            embedding=_make_embedding(0.51),
        )

        # Should have reinforced the first, not created new
        assert second.id == first.id
        assert second.signal_count == 2
        assert second.last_reinforced_at is not None

    def test_reinforced_memory_re_enters_review(self, mem_db, conversation_id):
        """Reinforced memories go back to pending_review."""
        embedding_service = _mock_embedding_service()
        service = MemoryService(
            provider=_mock_provider(is_match=False),
            embedding_service=embedding_service,
        )

        # Create and approve a memory
        first = service.store(
            conversation_id, "Initial insight.",
            embedding=_make_embedding(0.5),
        )
        service.approve(first.id)
        assert service.get_by_id(first.id).status == "approved"

        # Now mock duplicate detection
        embedding_service.find_similar.return_value = [(first.id, 0.9)]
        service._provider = _mock_provider(is_match=True, merged="Improved insight.")

        reinforced = service.store(
            conversation_id, "Similar insight again.",
            embedding=_make_embedding(0.51),
        )

        assert reinforced.status == "pending_review"
        assert reinforced.signal_count == 2

    def test_merged_narrative_updates(self, mem_db, conversation_id):
        """Merged narrative replaces the old one, original preserved."""
        embedding_service = _mock_embedding_service()
        service = MemoryService(
            provider=_mock_provider(is_match=False),
            embedding_service=embedding_service,
        )

        first = service.store(
            conversation_id, "Original narrative.",
            embedding=_make_embedding(0.5),
        )

        # Set up dedup match with merged narrative
        embedding_service.find_similar.return_value = [(first.id, 0.9)]
        service._provider = _mock_provider(
            is_match=True, merged="Better combined narrative."
        )

        reinforced = service.store(
            conversation_id, "Similar version.",
            embedding=_make_embedding(0.51),
        )

        assert reinforced.narrative == "Better combined narrative."
        assert reinforced.original_narrative == "Original narrative."

    def test_no_reinforce_when_llm_says_different(self, mem_db, conversation_id):
        """Creates new memory when LLM judges NOT a match despite similarity."""
        embedding_service = _mock_embedding_service()
        service = MemoryService(
            provider=_mock_provider(is_match=False),
            embedding_service=embedding_service,
        )

        first = service.store(
            conversation_id, "Alex prefers email.",
            embedding=_make_embedding(0.5),
        )

        # High embedding similarity but LLM says different
        embedding_service.find_similar.return_value = [(first.id, 0.88)]

        second = service.store(
            conversation_id, "Alex prefers Slack.",
            embedding=_make_embedding(0.52),
        )

        # Should be two different memories
        assert second.id != first.id
        assert second.signal_count == 1
        assert first.signal_count == 1

    def test_dedup_graceful_on_llm_error(self, mem_db, conversation_id):
        """Creates new memory if LLM judgment fails."""
        embedding_service = _mock_embedding_service()

        # Provider that throws
        bad_provider = MagicMock()
        bad_provider.chat_json.side_effect = RuntimeError("Ollama is down")

        service = MemoryService(
            provider=_mock_provider(is_match=False),
            embedding_service=embedding_service,
        )

        first = service.store(
            conversation_id, "First memory.",
            embedding=_make_embedding(0.5),
        )

        embedding_service.find_similar.return_value = [(first.id, 0.9)]
        service._provider = bad_provider

        # Should create new memory despite error (graceful degradation)
        second = service.store(
            conversation_id, "Second memory.",
            embedding=_make_embedding(0.51),
        )

        assert second.id != first.id
        assert second.signal_count == 1


# =============================================================================
# TestReviewGate
# =============================================================================


class TestReviewGate:
    """Test memory review state machine."""

    def test_approve(self, mem_db, conversation_id):
        """Approve transitions pending_review → approved."""
        service = MemoryService(
            provider=_mock_provider(),
            embedding_service=_mock_embedding_service(),
        )
        memory = service.store(conversation_id, "Approvable memory.")

        approved = service.approve(memory.id)
        assert approved.status == "approved"
        assert approved.user_reviewed is True

    def test_reject(self, mem_db, conversation_id):
        """Reject transitions pending_review → rejected."""
        service = MemoryService(
            provider=_mock_provider(),
            embedding_service=_mock_embedding_service(),
        )
        memory = service.store(conversation_id, "Rejectable memory.")

        rejected = service.reject(memory.id)
        assert rejected.status == "rejected"
        assert rejected.user_reviewed is True

    def test_cannot_approve_approved(self, mem_db, conversation_id):
        """Cannot approve an already approved memory."""
        service = MemoryService(
            provider=_mock_provider(),
            embedding_service=_mock_embedding_service(),
        )
        memory = service.store(conversation_id, "Memory.")
        service.approve(memory.id)

        with pytest.raises(MemoryError, match="pending_review"):
            service.approve(memory.id)

    def test_cannot_reject_approved(self, mem_db, conversation_id):
        """Cannot reject an approved memory."""
        service = MemoryService(
            provider=_mock_provider(),
            embedding_service=_mock_embedding_service(),
        )
        memory = service.store(conversation_id, "Memory.")
        service.approve(memory.id)

        with pytest.raises(MemoryError, match="pending_review"):
            service.reject(memory.id)

    def test_approve_nonexistent_raises(self, mem_db):
        """Approving nonexistent memory raises MemoryError."""
        service = MemoryService(
            provider=_mock_provider(),
            embedding_service=_mock_embedding_service(),
        )

        with pytest.raises(MemoryError, match="not found"):
            service.approve("nonexistent")

    def test_get_pending_review(self, mem_db, conversation_id):
        """List pending review memories."""
        service = MemoryService(
            provider=_mock_provider(),
            embedding_service=_mock_embedding_service(),
        )
        service.store(conversation_id, "Pending one.")
        m2 = service.store(conversation_id, "Pending two.")
        service.approve(m2.id)

        pending = service.get_pending_review()
        assert len(pending) == 1
        assert pending[0].narrative == "Pending one."


# =============================================================================
# TestNarrativeEditing
# =============================================================================


class TestNarrativeEditing:
    """Test editing memory narratives before approval."""

    def test_edit_narrative(self, mem_db, conversation_id):
        """Edit updates narrative and preserves original."""
        service = MemoryService(
            provider=_mock_provider(),
            embedding_service=_mock_embedding_service(),
        )
        memory = service.store(conversation_id, "Original text.")

        edited = service.edit_narrative(memory.id, "Improved text.")
        assert edited.narrative == "Improved text."
        assert edited.user_edited is True
        assert edited.original_narrative == "Original text."

    def test_cannot_edit_approved(self, mem_db, conversation_id):
        """Cannot edit an approved memory."""
        service = MemoryService(
            provider=_mock_provider(),
            embedding_service=_mock_embedding_service(),
        )
        memory = service.store(conversation_id, "Memory.")
        service.approve(memory.id)

        with pytest.raises(MemoryError, match="pending_review"):
            service.edit_narrative(memory.id, "New text.")


# =============================================================================
# TestRouting
# =============================================================================


class TestRouting:
    """Test memory routing to Acts."""

    def test_default_routes_to_your_story(self, mem_db, conversation_id):
        """Default routing goes to Your Story."""
        service = MemoryService(
            provider=_mock_provider(),
            embedding_service=_mock_embedding_service(),
        )
        memory = service.store(conversation_id, "General memory.")

        assert memory.is_your_story is True
        assert memory.destination_act_id is None

    def test_route_to_specific_act(self, mem_db, conversation_id):
        """Route memory to a specific Act."""
        # Create target Act
        with _transaction() as conn:
            conn.execute(
                """INSERT INTO acts (act_id, title, active, position, created_at, updated_at)
                   VALUES ('act-health', 'Health', 1, 1, '2024-01-01', '2024-01-01')"""
            )

        service = MemoryService(
            provider=_mock_provider(),
            embedding_service=_mock_embedding_service(),
        )
        memory = service.store(conversation_id, "Health memory.")

        routed = service.route(memory.id, "act-health")
        assert routed.destination_act_id == "act-health"
        assert routed.is_your_story is False

        # Verify block's act_id also updated
        conn = _get_connection()
        cursor = conn.execute(
            "SELECT act_id FROM blocks WHERE id = ?", (memory.block_id,)
        )
        assert cursor.fetchone()["act_id"] == "act-health"

    def test_route_to_your_story(self, mem_db, conversation_id):
        """Routing to Your Story sets is_your_story=True."""
        # Create an act to initially route to
        with _transaction() as conn:
            conn.execute(
                """INSERT INTO acts (act_id, title, active, position, created_at, updated_at)
                   VALUES ('act-temp', 'Temp', 1, 2, '2024-01-01', '2024-01-01')"""
            )

        service = MemoryService(
            provider=_mock_provider(),
            embedding_service=_mock_embedding_service(),
        )
        memory = service.store(
            conversation_id, "Memory.", destination_act_id="act-temp"
        )

        routed = service.route(memory.id, YOUR_STORY_ACT_ID)
        assert routed.is_your_story is True

    def test_route_nonexistent_raises(self, mem_db):
        """Routing nonexistent memory raises MemoryError."""
        service = MemoryService(
            provider=_mock_provider(),
            embedding_service=_mock_embedding_service(),
        )
        with pytest.raises(MemoryError, match="not found"):
            service.route("nonexistent", "some-act")


# =============================================================================
# TestSupersession
# =============================================================================


class TestSupersession:
    """Test memory correction and supersession chains."""

    def test_supersede(self, mem_db, conversation_id):
        """Supersede marks old memory and transfers signal_count."""
        service = MemoryService(
            provider=_mock_provider(),
            embedding_service=_mock_embedding_service(),
            graph_store=MagicMock(),
        )
        old = service.store(conversation_id, "Old understanding.")
        new = service.store(conversation_id, "New understanding.")

        result = service.supersede(old.id, new.id)

        # Old should be superseded
        old_updated = service.get_by_id(old.id)
        assert old_updated.status == "superseded"

        # New should have inherited signal_count
        assert result.signal_count == 2  # 1 (own) + 1 (inherited)

    def test_correct_creates_new_and_supersedes(self, mem_db, conversation_id):
        """Correct creates a new memory and supersedes the old one."""
        service = MemoryService(
            provider=_mock_provider(),
            embedding_service=_mock_embedding_service(),
            graph_store=MagicMock(),
        )
        original = service.store(conversation_id, "Alex prefers email.")

        corrected = service.correct(
            original.id,
            "Alex actually prefers Slack.",
            conversation_id,
        )

        assert corrected.narrative == "Alex actually prefers Slack."
        assert corrected.signal_count == 2  # inherited from original

        # Original should be superseded
        old = service.get_by_id(original.id)
        assert old.status == "superseded"

    def test_correct_nonexistent_raises(self, mem_db, conversation_id):
        """Correcting nonexistent memory raises MemoryError."""
        service = MemoryService(
            provider=_mock_provider(),
            embedding_service=_mock_embedding_service(),
        )
        with pytest.raises(MemoryError, match="not found"):
            service.correct("nonexistent", "New text.", conversation_id)

    def test_supersede_preserves_graph(self, mem_db, conversation_id):
        """Supersede creates a SUPERSEDES relationship in the graph."""
        graph_store = MagicMock()
        service = MemoryService(
            provider=_mock_provider(),
            embedding_service=_mock_embedding_service(),
            graph_store=graph_store,
        )
        old = service.store(conversation_id, "Old.")
        new = service.store(conversation_id, "New.")

        service.supersede(old.id, new.id)

        # Should have created SUPERSEDES relationship
        graph_store.create_relationship.assert_called()
        call_args = [
            c for c in graph_store.create_relationship.call_args_list
            if len(c.args) >= 3 and hasattr(c.args[2], 'value')
            and c.args[2].value == "supersedes"
        ]
        assert len(call_args) > 0


# =============================================================================
# TestListAndQuery
# =============================================================================


class TestListAndQuery:
    """Test listing and querying memories."""

    def test_list_all(self, mem_db, conversation_id):
        """List all memories."""
        service = MemoryService(
            provider=_mock_provider(),
            embedding_service=_mock_embedding_service(),
        )
        service.store(conversation_id, "Memory A.")
        service.store(conversation_id, "Memory B.")

        all_memories = service.list_memories()
        assert len(all_memories) == 2

    def test_list_by_status(self, mem_db, conversation_id):
        """List memories filtered by status."""
        service = MemoryService(
            provider=_mock_provider(),
            embedding_service=_mock_embedding_service(),
        )
        m1 = service.store(conversation_id, "Memory A.")
        service.store(conversation_id, "Memory B.")
        service.approve(m1.id)

        approved = service.list_memories(status="approved")
        assert len(approved) == 1
        assert approved[0].id == m1.id

        pending = service.list_memories(status="pending_review")
        assert len(pending) == 1

    def test_get_entities(self, mem_db, conversation_id):
        """Get entities for a memory (stored via compression manager path)."""
        service = MemoryService(
            provider=_mock_provider(),
            embedding_service=_mock_embedding_service(),
        )
        memory = service.store(conversation_id, "Memory with entities.")

        # Manually insert entities for testing
        with _transaction() as conn:
            conn.execute(
                """INSERT INTO memory_entities (id, memory_id, entity_type,
                   entity_data, created_at)
                   VALUES ('ent-1', ?, 'person', '{"name": "Alex"}', '2024-01-01')""",
                (memory.id,),
            )

        entities = service.get_entities(memory.id)
        assert len(entities) == 1
        assert entities[0]["entity_type"] == "person"
        assert entities[0]["entity_data"]["name"] == "Alex"

    def test_get_state_deltas(self, mem_db, conversation_id):
        """Get state deltas for a memory."""
        service = MemoryService(
            provider=_mock_provider(),
            embedding_service=_mock_embedding_service(),
        )
        memory = service.store(conversation_id, "Memory with deltas.")

        # Manually insert deltas for testing
        with _transaction() as conn:
            conn.execute(
                """INSERT INTO memory_state_deltas (id, memory_id, delta_type,
                   delta_data)
                   VALUES ('delta-1', ?, 'new_waiting_on',
                   '{"who": "Alex", "what": "feedback"}')""",
                (memory.id,),
            )

        deltas = service.get_state_deltas(memory.id)
        assert len(deltas) == 1
        assert deltas[0]["delta_type"] == "new_waiting_on"


# =============================================================================
# TestDeduplicationResult
# =============================================================================


class TestDeduplicationResult:
    """Test DeduplicationResult dataclass."""

    def test_not_duplicate(self):
        result = DeduplicationResult(is_duplicate=False, reason="No similar found")
        assert not result.is_duplicate
        assert result.matched_memory_id is None

    def test_duplicate(self):
        result = DeduplicationResult(
            is_duplicate=True,
            matched_memory_id="mem-123",
            reason="Same decision",
            merged_narrative="Merged text.",
        )
        assert result.is_duplicate
        assert result.matched_memory_id == "mem-123"


# =============================================================================
# TestMemoryDataclass
# =============================================================================


class TestMemoryDataclass:
    """Test Memory dataclass methods."""

    def test_to_dict(self, mem_db, conversation_id):
        """Memory.to_dict() includes all fields."""
        service = MemoryService(
            provider=_mock_provider(),
            embedding_service=_mock_embedding_service(),
        )
        memory = service.store(conversation_id, "Test memory.")

        d = memory.to_dict()
        assert d["narrative"] == "Test memory."
        assert d["status"] == "pending_review"
        assert d["signal_count"] == 1
        assert "id" in d
        assert "block_id" in d
        assert "created_at" in d

    def test_from_row(self, mem_db, conversation_id):
        """Memory.from_row() creates from database row."""
        service = MemoryService(
            provider=_mock_provider(),
            embedding_service=_mock_embedding_service(),
        )
        original = service.store(conversation_id, "From row test.")

        # Fetch via raw SQL to get a Row object
        conn = _get_connection()
        cursor = conn.execute(
            "SELECT * FROM memories WHERE id = ?", (original.id,)
        )
        row = cursor.fetchone()
        memory = Memory.from_row(row)

        assert memory.id == original.id
        assert memory.narrative == "From row test."
