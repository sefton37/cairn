"""Tests for conversation archive search functionality.

Covers ConversationService.search_messages(), list_with_summaries(),
and get_conversation_detail() — the three archive-search methods added in v13.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def search_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Set up a fresh v13 play database for archive search tests."""
    data_dir = tmp_path / "reos-data"
    data_dir.mkdir()
    monkeypatch.setenv("REOS_DATA_DIR", str(data_dir))

    import cairn.play_db as play_db

    play_db.close_connection()
    play_db.init_db()

    yield data_dir

    play_db.close_connection()


@pytest.fixture
def service(search_db):
    """ConversationService backed by the fresh test database."""
    from cairn.services.conversation_service import ConversationService

    return ConversationService()


def _archive_conversation(service, messages: list[tuple[str, str]]):
    """Helper: start, add messages, and drive through to archived state.

    Args:
        service: ConversationService instance.
        messages: List of (role, content) tuples.

    Returns:
        The archived Conversation.
    """
    conv = service.start()
    for role, content in messages:
        service.add_message(conv.id, role, content)
    service.close(conv.id)
    service.start_compression(conv.id)
    service.archive(conv.id)
    return service.get_by_id(conv.id)


def _write_summary(conversation_id: str, summary_text: str, model: str = "test-model") -> None:
    """Insert a conversation_summaries row directly for testing."""
    from datetime import UTC, datetime
    from uuid import uuid4

    import cairn.play_db as play_db

    conn = play_db._get_connection()
    now = datetime.now(UTC).isoformat()
    summary_id = uuid4().hex[:12]
    conn.execute(
        """INSERT OR REPLACE INTO conversation_summaries
           (id, conversation_id, summary, summary_model, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (summary_id, conversation_id, summary_text, model, now, now),
    )
    conn.commit()


def _write_memory(conversation_id: str, narrative: str) -> str:
    """Insert a minimal memory row and return its id."""
    from datetime import UTC, datetime
    from uuid import uuid4

    import cairn.play_db as play_db

    conn = play_db._get_connection()
    now = datetime.now(UTC).isoformat()
    memory_id = uuid4().hex[:12]
    block_id = "block-" + uuid4().hex[:12]

    # Memories require a block row (FK)
    conn.execute(
        """INSERT INTO blocks (id, type, act_id, parent_id, page_id, scene_id,
           position, created_at, updated_at)
           VALUES (?, 'memory', 'archived-conversations', NULL, NULL, NULL, 0, ?, ?)""",
        (block_id, now, now),
    )
    conn.execute(
        """INSERT INTO memories (id, block_id, conversation_id, narrative, status,
           signal_count, created_at)
           VALUES (?, ?, ?, ?, 'approved', 1, ?)""",
        (memory_id, block_id, conversation_id, narrative, now),
    )
    conn.commit()
    return memory_id


def _write_entity(memory_id: str, entity_type: str = "person") -> str:
    """Insert a memory_entity row and return its id."""
    from datetime import UTC, datetime
    from uuid import uuid4

    import cairn.play_db as play_db

    conn = play_db._get_connection()
    now = datetime.now(UTC).isoformat()
    entity_id = uuid4().hex[:12]
    conn.execute(
        """INSERT INTO memory_entities (id, memory_id, entity_type, entity_data, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (entity_id, memory_id, entity_type, json.dumps({"name": "Alice"}), now),
    )
    conn.commit()
    return entity_id


# =============================================================================
# search_messages
# =============================================================================


class TestSearchMessages:
    """Tests for ConversationService.search_messages()."""

    def test_search_finds_keyword(self, service, search_db):
        """FTS search returns a result when the keyword appears in archived messages."""
        _archive_conversation(
            service,
            [("user", "Tell me about quantum entanglement"), ("cairn", "It is fascinating")],
        )

        results = service.search_messages("quantum")

        assert len(results) == 1
        assert results[0]["conversation_id"] is not None

    def test_search_returns_snippets(self, service, search_db):
        """Results include a snippet field produced by FTS5 snippet()."""
        _archive_conversation(
            service,
            [("user", "I am learning about artificial intelligence every day")],
        )

        results = service.search_messages("artificial")

        assert len(results) == 1
        # snippet() wraps the match in <b>…</b>
        assert "<b>" in results[0]["snippet"]
        assert "artificial" in results[0]["snippet"].lower()

    def test_search_does_not_return_active_conversations(self, service, search_db):
        """search_messages(status='archived') excludes active conversations."""
        # Active conversation — never archived
        conv = service.start()
        service.add_message(conv.id, "user", "secret keyword banana")

        results = service.search_messages("banana")

        assert results == []

    def test_search_filters_by_since(self, service, search_db):
        """since parameter excludes conversations started before the cutoff."""
        from datetime import UTC, datetime, timedelta

        _archive_conversation(service, [("user", "the magic word is tangerine")])

        # A 'since' value one day in the future should exclude the conversation
        future = (datetime.now(UTC) + timedelta(days=1)).isoformat()
        results = service.search_messages("tangerine", since=future)

        assert results == []

    def test_search_filters_by_until(self, service, search_db):
        """until parameter excludes conversations started after the cutoff."""
        from datetime import UTC, datetime, timedelta

        _archive_conversation(service, [("user", "the word is papaya")])

        # An 'until' value one day in the past should exclude the conversation
        past = (datetime.now(UTC) - timedelta(days=1)).isoformat()
        results = service.search_messages("papaya", until=past)

        assert results == []

    def test_search_includes_role_and_position(self, service, search_db):
        """Each result dict exposes role and position from the messages table."""
        _archive_conversation(
            service,
            [
                ("user", "first mango message"),
                ("cairn", "second mango message"),
            ],
        )

        results = service.search_messages("mango")
        roles = {r["role"] for r in results}
        positions = {r["position"] for r in results}

        assert "user" in roles
        assert "cairn" in roles
        assert 0 in positions
        assert 1 in positions

    def test_search_limit_and_offset(self, service, search_db):
        """limit and offset parameters control result pagination."""
        _archive_conversation(
            service,
            [
                ("user", "pineapple one"),
                ("cairn", "pineapple two"),
                ("user", "pineapple three"),
            ],
        )

        all_results = service.search_messages("pineapple", limit=10)
        page_one = service.search_messages("pineapple", limit=2, offset=0)
        page_two = service.search_messages("pineapple", limit=2, offset=2)

        assert len(all_results) == 3
        assert len(page_one) == 2
        assert len(page_two) == 1

    def test_search_no_match_returns_empty(self, service, search_db):
        """search_messages returns an empty list when no message matches the query."""
        _archive_conversation(service, [("user", "completely unrelated content")])

        results = service.search_messages("zzznomatch")

        assert results == []


# =============================================================================
# list_with_summaries
# =============================================================================


class TestListWithSummaries:
    """Tests for ConversationService.list_with_summaries()."""

    def test_list_includes_summary_when_present(self, service, search_db):
        """list_with_summaries returns the summary text from conversation_summaries."""
        conv = _archive_conversation(service, [("user", "test content")])
        _write_summary(conv.id, "This was a short test conversation.")

        results = service.list_with_summaries()

        assert len(results) == 1
        assert results[0]["summary"] == "This was a short test conversation."

    def test_list_summary_is_none_when_absent(self, service, search_db):
        """list_with_summaries sets summary to None when no summary row exists."""
        _archive_conversation(service, [("user", "content with no summary")])

        results = service.list_with_summaries()

        assert len(results) == 1
        assert results[0]["summary"] is None

    def test_list_includes_memory_count(self, service, search_db):
        """list_with_summaries counts associated memories correctly."""
        conv = _archive_conversation(service, [("user", "some content")])
        _write_memory(conv.id, "First memory narrative")
        _write_memory(conv.id, "Second memory narrative")

        results = service.list_with_summaries()

        assert len(results) == 1
        assert results[0]["memory_count"] == 2

    def test_list_includes_entity_count(self, service, search_db):
        """list_with_summaries counts associated memory entities correctly."""
        conv = _archive_conversation(service, [("user", "entity test content")])
        memory_id = _write_memory(conv.id, "Memory with entities")
        _write_entity(memory_id, "person")
        _write_entity(memory_id, "task")

        results = service.list_with_summaries()

        assert len(results) == 1
        assert results[0]["entity_count"] == 2

    def test_list_filters_by_status(self, service, search_db):
        """list_with_summaries(status='active') excludes archived conversations."""
        _archive_conversation(service, [("user", "archived content")])
        active_conv = service.start()
        service.add_message(active_conv.id, "user", "active content")

        active_results = service.list_with_summaries(status="active")
        archived_results = service.list_with_summaries(status="archived")

        assert len(active_results) == 1
        assert active_results[0]["id"] == active_conv.id
        assert len(archived_results) == 1
        assert archived_results[0]["id"] != active_conv.id

    def test_list_has_memories_true_filter(self, service, search_db):
        """has_memories=True returns only conversations with at least one memory."""
        conv_with = _archive_conversation(service, [("user", "content a")])
        _write_memory(conv_with.id, "A memory")

        conv_without = _archive_conversation(service, [("user", "content b")])
        # No memory for conv_without

        results = service.list_with_summaries(has_memories=True)
        result_ids = {r["id"] for r in results}

        assert conv_with.id in result_ids
        assert conv_without.id not in result_ids

    def test_list_has_memories_false_filter(self, service, search_db):
        """has_memories=False returns only conversations with no memories."""
        conv_with = _archive_conversation(service, [("user", "content c")])
        _write_memory(conv_with.id, "A memory")

        conv_without = _archive_conversation(service, [("user", "content d")])

        results = service.list_with_summaries(has_memories=False)
        result_ids = {r["id"] for r in results}

        assert conv_without.id in result_ids
        assert conv_with.id not in result_ids

    def test_list_filters_by_since(self, service, search_db):
        """since parameter excludes conversations started before the cutoff."""
        from datetime import UTC, datetime, timedelta

        _archive_conversation(service, [("user", "old content")])
        future = (datetime.now(UTC) + timedelta(days=1)).isoformat()

        results = service.list_with_summaries(since=future)

        assert results == []

    def test_list_filters_by_until(self, service, search_db):
        """until parameter excludes conversations started after the cutoff."""
        from datetime import UTC, datetime, timedelta

        _archive_conversation(service, [("user", "recent content")])
        past = (datetime.now(UTC) - timedelta(days=1)).isoformat()

        results = service.list_with_summaries(until=past)

        assert results == []

    def test_list_ordered_most_recent_first(self, service, search_db):
        """list_with_summaries orders conversations by started_at descending."""
        conv1 = _archive_conversation(service, [("user", "first conversation")])
        conv2 = _archive_conversation(service, [("user", "second conversation")])

        results = service.list_with_summaries()

        assert results[0]["id"] == conv2.id
        assert results[1]["id"] == conv1.id

    def test_list_limit_and_offset(self, service, search_db):
        """limit and offset parameters paginate the result set."""
        _archive_conversation(service, [("user", "conv 1")])
        _archive_conversation(service, [("user", "conv 2")])
        _archive_conversation(service, [("user", "conv 3")])

        page_one = service.list_with_summaries(limit=2, offset=0)
        page_two = service.list_with_summaries(limit=2, offset=2)

        assert len(page_one) == 2
        assert len(page_two) == 1


# =============================================================================
# get_conversation_detail
# =============================================================================


class TestGetConversationDetail:
    """Tests for ConversationService.get_conversation_detail()."""

    def test_detail_returns_full_history(self, service, search_db):
        """get_conversation_detail returns all messages in order."""
        conv = _archive_conversation(
            service,
            [
                ("user", "Hello there"),
                ("cairn", "Hello back"),
                ("user", "Goodbye"),
            ],
        )

        detail = service.get_conversation_detail(conv.id)

        assert detail["conversation"] is not None
        assert detail["conversation"]["id"] == conv.id
        messages = detail["messages"]
        assert len(messages) == 3
        assert messages[0]["content"] == "Hello there"
        assert messages[1]["content"] == "Hello back"
        assert messages[2]["content"] == "Goodbye"

    def test_detail_includes_memories(self, service, search_db):
        """get_conversation_detail includes all associated memories."""
        conv = _archive_conversation(service, [("user", "memory content")])
        mem1 = _write_memory(conv.id, "First memory")
        mem2 = _write_memory(conv.id, "Second memory")

        detail = service.get_conversation_detail(conv.id)

        memory_ids = {m["id"] for m in detail["memories"]}
        assert mem1 in memory_ids
        assert mem2 in memory_ids

    def test_detail_includes_entities_on_memories(self, service, search_db):
        """Each memory in the detail dict contains its entities list."""
        conv = _archive_conversation(service, [("user", "entity content")])
        memory_id = _write_memory(conv.id, "Memory with entities")
        entity_id = _write_entity(memory_id, "person")

        detail = service.get_conversation_detail(conv.id)

        assert len(detail["memories"]) == 1
        entities = detail["memories"][0]["entities"]
        entity_ids = [e["id"] for e in entities]
        assert entity_id in entity_ids

    def test_detail_includes_deltas_on_memories(self, service, search_db):
        """Each memory in the detail dict contains its state_deltas list."""
        from uuid import uuid4

        import cairn.play_db as play_db

        conv = _archive_conversation(service, [("user", "delta content")])
        memory_id = _write_memory(conv.id, "Memory with delta")

        # Write a state delta directly
        conn = play_db._get_connection()
        delta_id = uuid4().hex[:12]
        conn.execute(
            """INSERT INTO memory_state_deltas (id, memory_id, delta_type, delta_data)
               VALUES (?, ?, ?, ?)""",
            (delta_id, memory_id, "belief_update", json.dumps({"key": "value"})),
        )
        conn.commit()

        detail = service.get_conversation_detail(conv.id)

        assert len(detail["memories"]) == 1
        deltas = detail["memories"][0]["deltas"]
        delta_ids = [d["id"] for d in deltas]
        assert delta_id in delta_ids

    def test_detail_includes_summary(self, service, search_db):
        """get_conversation_detail returns the summary string when one exists."""
        conv = _archive_conversation(service, [("user", "summary content")])
        _write_summary(conv.id, "A thorough summary of the conversation.")

        detail = service.get_conversation_detail(conv.id)

        assert detail["summary"] == "A thorough summary of the conversation."

    def test_detail_summary_is_none_when_absent(self, service, search_db):
        """summary is None in the detail dict when no summary row exists."""
        conv = _archive_conversation(service, [("user", "no summary")])

        detail = service.get_conversation_detail(conv.id)

        assert detail["summary"] is None

    def test_detail_unknown_id_returns_null_conversation(self, service, search_db):
        """get_conversation_detail returns conversation=None for an unknown ID."""
        detail = service.get_conversation_detail("does-not-exist")

        assert detail["conversation"] is None
        assert detail["messages"] == []
        assert detail["memories"] == []
        assert detail["summary"] is None
