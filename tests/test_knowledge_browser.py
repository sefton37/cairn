"""Tests for the Knowledge Base Browser feature.

Covers:
- search_fts: FTS5 keyword search on memory narratives
- list_enhanced: Enhanced listing with entity/delta counts, supersession info
- get_supersession_chain: Full chain traversal
- get_influence_log: Classification influence audit trail
- get_entity_type_counts: Entity type counts for filter UI
- get_act_memory_groups: Memories grouped by destination Act
- open_threads RPC handler
- resolve_thread RPC handler
"""

from __future__ import annotations

import json
import struct
from unittest.mock import MagicMock

import pytest

from cairn.play_db import (
    _get_connection,
    _transaction,
    close_connection,
    init_db,
)
from cairn.services.memory_service import MemoryService


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


def _mock_embedding_service(similar_results: list | None = None) -> MagicMock:
    """Mock EmbeddingService with no similar results by default."""
    svc = MagicMock()
    svc.embed.return_value = _make_embedding(0.5)
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


def _make_service_with_real_graph(
    *,
    is_match: bool = False,
    merged: str = "",
    similar_results: list | None = None,
) -> MemoryService:
    """MemoryService with a real MemoryGraphStore so SUPERSEDES edges are persisted."""
    from cairn.memory.graph_store import MemoryGraphStore

    return MemoryService(
        provider=_mock_provider(is_match=is_match, merged=merged),
        embedding_service=_mock_embedding_service(similar_results=similar_results),
        graph_store=MemoryGraphStore(),
    )


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def _fresh_db(tmp_path, monkeypatch):
    """Fresh isolated database for each test."""
    monkeypatch.setenv("REOS_DATA_DIR", str(tmp_path))
    close_connection()
    init_db()
    yield
    close_connection()


@pytest.fixture()
def conversation_id():
    """Create a conversation and return its ID."""
    from cairn.services.conversation_service import ConversationService

    service = ConversationService()
    conv = service.start()
    service.add_message(conv.id, "user", "Let's discuss the project.")
    return conv.id


@pytest.fixture()
def second_conversation_id(conversation_id):
    """Create a second conversation after archiving the first."""
    from cairn.services.conversation_service import ConversationService

    with _transaction() as conn:
        conn.execute(
            "UPDATE conversations SET status = 'archived' WHERE id = ?",
            (conversation_id,),
        )

    svc = ConversationService()
    conv = svc.start()
    svc.add_message(conv.id, "user", "Second conversation.")
    return conv.id


# =============================================================================
# TestSearchFts
# =============================================================================


class TestSearchFts:
    """FTS5 keyword search on memory narratives."""

    def test_search_fts_finds_keyword(self, conversation_id):
        """Insert a memory with a known narrative; FTS search returns it."""
        svc = _make_service()
        mem = svc.store(conversation_id, "The team decided to adopt GraphQL for the API.")
        # Approve so we can optionally filter; also test without status filter
        svc.approve(mem.id)

        results = svc.search_fts("GraphQL")

        assert len(results) == 1
        assert results[0]["id"] == mem.id
        assert "GraphQL" in results[0]["narrative"]
        # snippet must be present (may contain the keyword or surrounding text)
        assert results[0]["snippet"] is not None
        assert results[0]["rank"] is not None

    def test_search_fts_no_match_returns_empty(self, conversation_id):
        """FTS search for absent keyword returns empty list."""
        svc = _make_service()
        svc.store(conversation_id, "We use SQLite for local storage.")

        results = svc.search_fts("PostgreSQL")

        assert results == []

    def test_search_fts_status_filter(self, conversation_id):
        """Status filter limits results to the given status."""
        svc = _make_service()
        mem = svc.store(conversation_id, "We deploy on Kubernetes in production.")
        # leave as pending_review

        # Should find it with no status filter
        results_all = svc.search_fts("Kubernetes")
        assert len(results_all) == 1

        # Should NOT find it when filtering for approved only
        results_approved = svc.search_fts("Kubernetes", status="approved")
        assert results_approved == []

        # Approve and it shows up
        svc.approve(mem.id)
        results_after = svc.search_fts("Kubernetes", status="approved")
        assert len(results_after) == 1

    def test_search_fts_limit_and_offset(self, conversation_id, second_conversation_id):
        """limit and offset control pagination of FTS results."""
        svc = _make_service()
        # Store two memories both matching "lambda"
        svc.store(conversation_id, "We use lambda functions for event processing.")
        svc.store(second_conversation_id, "Lambda is our default compute pattern.")

        all_results = svc.search_fts("lambda", limit=10)
        assert len(all_results) == 2

        page1 = svc.search_fts("lambda", limit=1, offset=0)
        page2 = svc.search_fts("lambda", limit=1, offset=1)
        assert len(page1) == 1
        assert len(page2) == 1
        assert page1[0]["id"] != page2[0]["id"]


# =============================================================================
# TestListEnhanced
# =============================================================================


class TestListEnhanced:
    """Enhanced listing with entity_count, delta_count, supersession info."""

    def test_list_enhanced_returns_entity_count(self, conversation_id):
        """Returned records include entity_count from memory_entities."""
        svc = _make_service()
        mem = svc.store(conversation_id, "Alex joined the backend team.")

        # Insert two entities for this memory
        conn = _get_connection()
        from uuid import uuid4
        now = "2026-01-01T00:00:00+00:00"
        for _ in range(2):
            conn.execute(
                """INSERT INTO memory_entities (id, memory_id, entity_type, entity_data, created_at)
                   VALUES (?, ?, 'person', '{"name": "Alex"}', ?)""",
                (uuid4().hex[:12], mem.id, now),
            )
        conn.commit()

        results = svc.list_enhanced()
        row = next(r for r in results if r["id"] == mem.id)
        assert row["entity_count"] == 2

    def test_list_enhanced_filters_by_source(self, conversation_id, second_conversation_id):
        """filter by source returns only memories with that source value."""
        svc = _make_service()
        mem_comp = svc.store(conversation_id, "Compression memory.", source="compression")
        mem_turn = svc.store(
            second_conversation_id, "Turn assessment memory.", source="turn_assessment"
        )

        comp_results = svc.list_enhanced(source="compression")
        turn_results = svc.list_enhanced(source="turn_assessment")

        comp_ids = {r["id"] for r in comp_results}
        turn_ids = {r["id"] for r in turn_results}

        assert mem_comp.id in comp_ids
        assert mem_comp.id not in turn_ids
        assert mem_turn.id in turn_ids
        assert mem_turn.id not in comp_ids

    def test_list_enhanced_orders_by_signal(self, conversation_id, second_conversation_id):
        """order_by='signal_count' returns memories in descending signal order."""
        svc = _make_service()
        mem_low = svc.store(conversation_id, "Low signal memory.")
        mem_high = svc.store(second_conversation_id, "High signal memory.")

        # Manually bump signal_count
        with _transaction() as conn:
            conn.execute(
                "UPDATE memories SET signal_count = 10 WHERE id = ?",
                (mem_high.id,),
            )
            conn.execute(
                "UPDATE memories SET signal_count = 1 WHERE id = ?",
                (mem_low.id,),
            )

        results = svc.list_enhanced(order_by="signal_count")
        ids = [r["id"] for r in results]

        assert ids.index(mem_high.id) < ids.index(mem_low.id)

    def test_list_enhanced_filters_by_entity_type(self, conversation_id):
        """entity_type filter returns only memories that have a matching entity."""
        svc = _make_service()
        mem_with = svc.store(conversation_id, "Memory with a task entity.")
        mem_without = svc.store(conversation_id, "Memory with no task entity.")

        conn = _get_connection()
        from uuid import uuid4
        now = "2026-01-01T00:00:00+00:00"
        conn.execute(
            """INSERT INTO memory_entities (id, memory_id, entity_type, entity_data, created_at)
               VALUES (?, ?, 'task', '{"title": "Fix bug"}', ?)""",
            (uuid4().hex[:12], mem_with.id, now),
        )
        conn.commit()

        results = svc.list_enhanced(entity_type="task")
        result_ids = {r["id"] for r in results}

        assert mem_with.id in result_ids
        assert mem_without.id not in result_ids

    def test_list_enhanced_filters_by_min_signal(self, conversation_id, second_conversation_id):
        """min_signal filter excludes memories below the threshold."""
        svc = _make_service()
        mem_low = svc.store(conversation_id, "Low signal.")
        mem_high = svc.store(second_conversation_id, "High signal.")

        with _transaction() as conn:
            conn.execute("UPDATE memories SET signal_count = 1 WHERE id = ?", (mem_low.id,))
            conn.execute("UPDATE memories SET signal_count = 5 WHERE id = ?", (mem_high.id,))

        results = svc.list_enhanced(min_signal=3)
        result_ids = {r["id"] for r in results}

        assert mem_high.id in result_ids
        assert mem_low.id not in result_ids

    def test_list_enhanced_superseded_flag(self, conversation_id, second_conversation_id):
        """is_superseded is True for superseded memories, False for active ones."""
        svc = _make_service_with_real_graph()
        original = svc.store(conversation_id, "Original fact.")
        corrected = svc.correct(original.id, "Corrected fact.", conversation_id)

        results = svc.list_enhanced()
        by_id = {r["id"]: r for r in results}

        assert by_id[original.id]["is_superseded"] is True
        assert by_id[corrected.id]["is_superseded"] is False

    def test_list_enhanced_superseded_by_populated(self, conversation_id, second_conversation_id):
        """superseded_by contains the ID of the superseding memory."""
        svc = _make_service_with_real_graph()
        original = svc.store(conversation_id, "Will be superseded.")
        corrected = svc.correct(original.id, "The correction.", conversation_id)

        results = svc.list_enhanced()
        by_id = {r["id"]: r for r in results}

        assert by_id[original.id]["superseded_by"] == corrected.id


# =============================================================================
# TestSupersessionChain
# =============================================================================


class TestSupersessionChain:
    """Full supersession chain traversal, oldest to newest."""

    def test_supersession_chain_single_memory(self, conversation_id):
        """A non-superseded memory returns a chain of length 1."""
        svc = _make_service_with_real_graph()
        mem = svc.store(conversation_id, "Standalone memory.")

        chain = svc.get_supersession_chain(mem.id)

        assert len(chain) == 1
        assert chain[0]["id"] == mem.id

    def test_supersession_chain_two_hop(self, conversation_id):
        """A → B chain returns [A, B] in chronological order."""
        svc = _make_service_with_real_graph()
        mem_a = svc.store(conversation_id, "Original version.")
        mem_b = svc.correct(mem_a.id, "Corrected version.", conversation_id)

        # Query from either end
        chain_from_a = svc.get_supersession_chain(mem_a.id)
        chain_from_b = svc.get_supersession_chain(mem_b.id)

        assert len(chain_from_a) == 2
        assert chain_from_a[0]["id"] == mem_a.id
        assert chain_from_a[1]["id"] == mem_b.id

        assert len(chain_from_b) == 2
        assert chain_from_b[0]["id"] == mem_a.id
        assert chain_from_b[1]["id"] == mem_b.id

    def test_supersession_chain_three_hop(self, conversation_id):
        """A → B → C chain returns [A, B, C] from any starting point."""
        svc = _make_service_with_real_graph()

        mem_a = svc.store(conversation_id, "Version A.")
        mem_b = svc.correct(mem_a.id, "Version B.", conversation_id)
        mem_c = svc.correct(mem_b.id, "Version C.", conversation_id)

        chain = svc.get_supersession_chain(mem_a.id)

        assert len(chain) == 3
        assert chain[0]["id"] == mem_a.id
        assert chain[1]["id"] == mem_b.id
        assert chain[2]["id"] == mem_c.id

    def test_supersession_chain_unknown_id_returns_empty(self):
        """Unknown memory_id returns empty list."""
        svc = _make_service_with_real_graph()
        chain = svc.get_supersession_chain("nonexistent_id")
        assert chain == []


# =============================================================================
# TestInfluenceLog
# =============================================================================


class TestInfluenceLog:
    """Classification influence audit trail."""

    def test_influence_log_returns_entries(self, conversation_id):
        """Inserted classification_memory_references are returned."""
        from cairn.services.memory_service import log_memory_influence

        svc = _make_service()
        mem = svc.store(conversation_id, "Memory that will be referenced.")
        svc.approve(mem.id)

        # Insert two influence log entries via the module-level helper
        log_memory_influence(
            classification_id="cls-001",
            memory_references=[
                {
                    "memory_id": mem.id,
                    "influence_type": "semantic_match",
                    "influence_score": 0.87,
                    "reasoning": "High similarity to query.",
                }
            ],
        )
        log_memory_influence(
            classification_id="cls-002",
            memory_references=[
                {
                    "memory_id": mem.id,
                    "influence_type": "graph_expansion",
                    "influence_score": 0.5,
                    "reasoning": "Reached via graph traversal.",
                }
            ],
        )

        entries = svc.get_influence_log(mem.id)

        assert len(entries) == 2
        classification_ids = {e["classification_id"] for e in entries}
        assert "cls-001" in classification_ids
        assert "cls-002" in classification_ids

    def test_influence_log_respects_limit(self, conversation_id):
        """limit parameter caps the number of returned entries."""
        from cairn.services.memory_service import log_memory_influence

        svc = _make_service()
        mem = svc.store(conversation_id, "Frequently referenced memory.")

        for i in range(5):
            log_memory_influence(
                classification_id=f"cls-{i:03d}",
                memory_references=[
                    {"memory_id": mem.id, "influence_type": "semantic_match",
                     "influence_score": 0.9, "reasoning": f"Entry {i}"}
                ],
            )

        entries = svc.get_influence_log(mem.id, limit=3)
        assert len(entries) == 3

    def test_influence_log_empty_for_uninfluential_memory(self, conversation_id):
        """Memory with no log entries returns empty list."""
        svc = _make_service()
        mem = svc.store(conversation_id, "Never used in classification.")

        entries = svc.get_influence_log(mem.id)
        assert entries == []


# =============================================================================
# TestEntityTypeCounts
# =============================================================================


class TestEntityTypeCounts:
    """Entity type counts for filter UI."""

    def test_entity_type_counts(self, conversation_id):
        """Counts reflect actual entities attached to approved memories."""
        from uuid import uuid4

        svc = _make_service()
        mem = svc.store(conversation_id, "Complex memory with many entities.")
        svc.approve(mem.id)

        conn = _get_connection()
        now = "2026-01-01T00:00:00+00:00"
        for entity_type, count in [("person", 2), ("task", 3), ("decision", 1)]:
            for _ in range(count):
                conn.execute(
                    """INSERT INTO memory_entities
                       (id, memory_id, entity_type, entity_data, created_at)
                       VALUES (?, ?, ?, '{}', ?)""",
                    (uuid4().hex[:12], mem.id, entity_type, now),
                )
        conn.commit()

        counts = svc.get_entity_type_counts(status="approved")

        assert counts["person"] == 2
        assert counts["task"] == 3
        assert counts["decision"] == 1

    def test_entity_type_counts_excludes_wrong_status(self, conversation_id):
        """Entities on pending_review memories are excluded when filtering approved."""
        from uuid import uuid4

        svc = _make_service()
        mem = svc.store(conversation_id, "Pending review memory.")
        # leave as pending_review

        conn = _get_connection()
        now = "2026-01-01T00:00:00+00:00"
        conn.execute(
            """INSERT INTO memory_entities
               (id, memory_id, entity_type, entity_data, created_at)
               VALUES (?, ?, 'person', '{"name": "Bob"}', ?)""",
            (uuid4().hex[:12], mem.id, now),
        )
        conn.commit()

        counts = svc.get_entity_type_counts(status="approved")
        assert counts.get("person", 0) == 0

    def test_entity_type_counts_empty_when_no_entities(self, conversation_id):
        """Returns empty dict when no approved memories have entities."""
        svc = _make_service()
        mem = svc.store(conversation_id, "Memory with no entities.")
        svc.approve(mem.id)

        counts = svc.get_entity_type_counts(status="approved")
        assert counts == {}


# =============================================================================
# TestActMemoryGroups
# =============================================================================


class TestActMemoryGroups:
    """Memories grouped by destination Act."""

    def test_by_act_groups_your_story(self, conversation_id):
        """Memories with is_your_story=1 group under the Your Story act."""
        from cairn.play_db import YOUR_STORY_ACT_ID

        svc = _make_service()
        mem = svc.store(conversation_id, "A personal insight.")
        svc.approve(mem.id)

        groups = svc.get_act_memory_groups(status="approved")

        # Should have at least one group
        assert len(groups) >= 1
        group_act_ids = {g["act_id"] for g in groups}
        assert YOUR_STORY_ACT_ID in group_act_ids

    def test_by_act_includes_memory_count(self, conversation_id, second_conversation_id):
        """memory_count in each group reflects approved memories routed there."""
        svc = _make_service()
        mem1 = svc.store(conversation_id, "First memory for Your Story.")
        mem2 = svc.store(second_conversation_id, "Second memory for Your Story.")
        svc.approve(mem1.id)
        svc.approve(mem2.id)

        from cairn.play_db import YOUR_STORY_ACT_ID
        groups = svc.get_act_memory_groups(status="approved")
        ys_group = next(g for g in groups if g["act_id"] == YOUR_STORY_ACT_ID)

        assert ys_group["memory_count"] >= 2

    def test_by_act_excludes_non_approved(self, conversation_id):
        """Pending review memories are not counted."""
        svc = _make_service()
        svc.store(conversation_id, "Pending memory, should not count.")
        # leave as pending_review

        groups = svc.get_act_memory_groups(status="approved")
        total = sum(g["memory_count"] for g in groups)
        assert total == 0

    def test_by_act_custom_act(self, conversation_id):
        """Memories routed to a custom Act appear in that Act's group."""
        from cairn.play_db import create_act

        _, custom_act_id = create_act(title="Career Act")

        svc = _make_service()
        mem = svc.store(
            conversation_id,
            "Career milestone reached.",
            destination_act_id=custom_act_id,
        )
        svc.approve(mem.id)

        groups = svc.get_act_memory_groups(status="approved")
        group_act_ids = {g["act_id"] for g in groups}
        assert custom_act_id in group_act_ids

        career_group = next(g for g in groups if g["act_id"] == custom_act_id)
        assert career_group["act_title"] == "Career Act"
        assert career_group["memory_count"] == 1


# =============================================================================
# TestOpenThreadsRpc
# =============================================================================


class TestOpenThreadsRpc:
    """Open threads via RPC handler."""

    def test_open_threads_rpc(self, conversation_id):
        """Unresolved state deltas are returned via the open_threads RPC."""
        from cairn.rpc_handlers.memories import handle_memories_open_threads
        from cairn.play_db import _get_connection as _gc
        from uuid import uuid4

        svc = _make_service()
        mem = svc.store(conversation_id, "Memory with open thread.")

        # Insert an unresolved state delta
        conn = _gc()
        delta_id = uuid4().hex[:12]
        conn.execute(
            """INSERT INTO memory_state_deltas (id, memory_id, delta_type, delta_data, applied)
               VALUES (?, ?, 'waiting_on', '{"subject": "PR review"}', 0)""",
            (delta_id, mem.id),
        )
        conn.commit()

        result = handle_memories_open_threads(None)

        assert "threads" in result
        thread_ids = [t["id"] for t in result["threads"]]
        assert delta_id in thread_ids

    def test_open_threads_rpc_excludes_resolved(self, conversation_id):
        """Resolved state deltas (applied=1) are not returned."""
        from cairn.rpc_handlers.memories import handle_memories_open_threads
        from cairn.play_db import _get_connection as _gc
        from uuid import uuid4

        svc = _make_service()
        mem = svc.store(conversation_id, "Memory with resolved thread.")

        conn = _gc()
        delta_id = uuid4().hex[:12]
        conn.execute(
            """INSERT INTO memory_state_deltas
               (id, memory_id, delta_type, delta_data, applied, applied_at)
               VALUES (?, ?, 'question_opened', '{"q": "done?"}', 1,
                       '2026-01-01T00:00:00+00:00')""",
            (delta_id, mem.id),
        )
        conn.commit()

        result = handle_memories_open_threads(None)
        thread_ids = [t["id"] for t in result["threads"]]
        assert delta_id not in thread_ids


# =============================================================================
# TestResolveThreadRpc
# =============================================================================


class TestResolveThreadRpc:
    """Thread resolution via RPC handler."""

    def test_resolve_thread_rpc(self, conversation_id):
        """Resolving a thread marks the delta as applied and returns result."""
        from cairn.rpc_handlers.memories import (
            handle_memories_resolve_thread,
            handle_memories_open_threads,
        )
        from cairn.play_db import _get_connection as _gc
        from uuid import uuid4

        svc = _make_service()
        mem = svc.store(conversation_id, "Memory with resolvable thread.")

        conn = _gc()
        delta_id = uuid4().hex[:12]
        conn.execute(
            """INSERT INTO memory_state_deltas (id, memory_id, delta_type, delta_data, applied)
               VALUES (?, ?, 'waiting_on', '{"subject": "Deploy approval"}', 0)""",
            (delta_id, mem.id),
        )
        conn.commit()

        result = handle_memories_resolve_thread(
            None,
            memory_id=mem.id,
            delta_id=delta_id,
            resolution_note="Deploy was approved on 2026-02-27.",
        )

        assert "delta" in result
        assert result["delta"]["applied"] is True
        assert result["delta"]["delta_data"]["resolved"] is True
        assert result["delta"]["delta_data"]["resolution_note"] == (
            "Deploy was approved on 2026-02-27."
        )

        # Verify it no longer shows in open threads
        open_result = handle_memories_open_threads(None)
        open_ids = [t["id"] for t in open_result["threads"]]
        assert delta_id not in open_ids

    def test_resolve_thread_rpc_already_resolved_returns_error(self, conversation_id):
        """Resolving an already-resolved delta returns an error (not raises)."""
        from cairn.rpc_handlers.memories import handle_memories_resolve_thread
        from cairn.play_db import _get_connection as _gc
        from uuid import uuid4

        svc = _make_service()
        mem = svc.store(conversation_id, "Memory for double-resolve test.")

        conn = _gc()
        delta_id = uuid4().hex[:12]
        conn.execute(
            """INSERT INTO memory_state_deltas (id, memory_id, delta_type, delta_data, applied)
               VALUES (?, ?, 'waiting_on', '{"subject": "test"}', 0)""",
            (delta_id, mem.id),
        )
        conn.commit()

        # First resolve should succeed
        result1 = handle_memories_resolve_thread(None, memory_id=mem.id, delta_id=delta_id)
        assert "error" not in result1

        # Second resolve should return an error dict (not raise)
        result2 = handle_memories_resolve_thread(None, memory_id=mem.id, delta_id=delta_id)
        assert "error" in result2
