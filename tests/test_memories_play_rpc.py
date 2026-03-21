"""Tests for Play-integration memory RPC handlers (Step 7).

Covers:
- handle_memories_by_act_page: returns memories for an act, grouped by their
  Memories page, with optional status filter
- handle_memories_ensure_page: idempotently provisions the Memories page
"""

from __future__ import annotations

import json
import struct
from unittest.mock import MagicMock

import pytest

from cairn.play_db import (
    _get_connection,
    close_connection,
    create_act,
    init_db,
)
from cairn.rpc_handlers.memories import (
    handle_memories_by_act_page,
    handle_memories_ensure_page,
)
from cairn.services.memory_service import MemoryService

# =============================================================================
# Helpers
# =============================================================================


def _make_embedding(value: float = 0.5) -> bytes:
    """Create a fake 384-dim embedding."""
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


def _make_service() -> MemoryService:
    return MemoryService(
        provider=_mock_provider(),
        embedding_service=_mock_embedding_service(),
        graph_store=MagicMock(),
    )


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def _fresh_db(tmp_path, monkeypatch):
    """Fresh isolated database for each test."""
    monkeypatch.setenv("TALKINGROCK_DATA_DIR", str(tmp_path))
    close_connection()
    init_db()
    yield
    close_connection()


@pytest.fixture()
def act_id():
    """Create a test Act and return its ID."""
    _, aid = create_act(title="Test Act")
    return aid


@pytest.fixture()
def conversation_id():
    """Create a conversation and return its ID."""
    from cairn.services.conversation_service import ConversationService

    service = ConversationService()
    conv = service.start()
    service.add_message(conv.id, "user", "Test message.")
    return conv.id


# =============================================================================
# TestMemoriesByActPage
# =============================================================================


class TestMemoriesByActPage:
    """handle_memories_by_act_page returns memories routed to a given act."""

    def test_returns_memories_for_act(self, act_id, conversation_id):
        """Memories routed to an act appear in the by_act_page response."""
        svc = _make_service()
        mem = svc.store(conversation_id, "We adopted async processing for the queue.")
        svc.route(mem.id, act_id)

        result = handle_memories_by_act_page(None, act_id=act_id)

        assert "memories" in result
        assert "memories_page_id" in result
        ids = [m["id"] for m in result["memories"]]
        assert mem.id in ids

    def test_memory_dict_has_expected_fields(self, act_id, conversation_id):
        """Each memory dict contains exactly the expected fields."""
        svc = _make_service()
        mem = svc.store(conversation_id, "The team chose Python 3.12.")
        svc.route(mem.id, act_id)

        result = handle_memories_by_act_page(None, act_id=act_id)

        assert len(result["memories"]) == 1
        m = result["memories"][0]
        assert set(m.keys()) == {
            "id",
            "narrative",
            "memory_type",
            "status",
            "signal_count",
            "created_at",
            "block_id",
        }

    def test_no_memories_returns_empty_list(self, act_id):
        """Act with no memories returns an empty memories list."""
        result = handle_memories_by_act_page(None, act_id=act_id)

        assert result["memories"] == []

    def test_status_filter_excludes_non_matching(self, act_id, conversation_id):
        """Status filter excludes memories whose status does not match."""
        svc = _make_service()
        pending_mem = svc.store(conversation_id, "Pending memory about backlog.")
        svc.route(pending_mem.id, act_id)

        # pending_review memory should NOT appear when filtering for approved
        result = handle_memories_by_act_page(None, act_id=act_id, status="approved")
        ids = [m["id"] for m in result["memories"]]
        assert pending_mem.id not in ids

    def test_status_filter_includes_matching(self, act_id, conversation_id):
        """Approving a memory makes it appear when filtering for approved."""
        svc = _make_service()
        mem = svc.store(conversation_id, "Memory about code review process.")
        svc.route(mem.id, act_id)
        svc.approve(mem.id)

        result = handle_memories_by_act_page(None, act_id=act_id, status="approved")
        ids = [m["id"] for m in result["memories"]]
        assert mem.id in ids

    def test_status_filter_pending_review(self, act_id, conversation_id):
        """Status filter for pending_review returns only unreviewed memories."""
        svc = _make_service()
        mem = svc.store(conversation_id, "Unreviewed insight about velocity.")
        svc.route(mem.id, act_id)

        result = handle_memories_by_act_page(None, act_id=act_id, status="pending_review")
        ids = [m["id"] for m in result["memories"]]
        assert mem.id in ids

    def test_memories_page_id_none_when_not_provisioned(self, act_id):
        """memories_page_id is None when the Memories page has not been created."""
        result = handle_memories_by_act_page(None, act_id=act_id)

        assert result["memories_page_id"] is None

    def test_memories_page_id_present_after_provisioning(self, act_id):
        """memories_page_id is returned once the Memories page has been created."""
        from cairn.play_db import ensure_memories_page

        page_id = ensure_memories_page(act_id)

        result = handle_memories_by_act_page(None, act_id=act_id)

        assert result["memories_page_id"] == page_id

    def test_does_not_return_memories_from_other_acts(self, act_id, conversation_id):
        """Memories routed to a different act do not appear in this act's results."""
        svc = _make_service()
        _, other_act_id = create_act(title="Other Act")

        mem_this = svc.store(conversation_id, "Memory for this act.")
        svc.route(mem_this.id, act_id)

        mem_other = svc.store(conversation_id, "Memory for the other act.")
        svc.route(mem_other.id, other_act_id)

        result = handle_memories_by_act_page(None, act_id=act_id)
        ids = [m["id"] for m in result["memories"]]

        assert mem_this.id in ids
        assert mem_other.id not in ids


# =============================================================================
# TestMemoriesEnsurePage
# =============================================================================


class TestMemoriesEnsurePage:
    """handle_memories_ensure_page provisions the Memories page for an act."""

    def test_creates_page_and_returns_page_id(self, act_id):
        """Calling ensure_page on an act without a Memories page creates one."""
        result = handle_memories_ensure_page(None, act_id=act_id)

        assert "page_id" in result
        assert isinstance(result["page_id"], str)
        assert result["page_id"]  # non-empty

    def test_is_idempotent(self, act_id):
        """Calling ensure_page twice returns the same page_id."""
        result1 = handle_memories_ensure_page(None, act_id=act_id)
        result2 = handle_memories_ensure_page(None, act_id=act_id)

        assert result1["page_id"] == result2["page_id"]

    def test_page_has_memories_system_role(self, act_id):
        """The provisioned page has system_page_role = 'memories' in the DB."""
        result = handle_memories_ensure_page(None, act_id=act_id)
        page_id = result["page_id"]

        conn = _get_connection()
        row = conn.execute(
            "SELECT system_page_role FROM pages WHERE page_id = ?", (page_id,)
        ).fetchone()

        assert row is not None
        assert row["system_page_role"] == "memories"

    def test_returned_page_id_matches_by_act_page_lookup(self, act_id):
        """The page_id from ensure_page matches what by_act_page returns."""
        ensure_result = handle_memories_ensure_page(None, act_id=act_id)
        page_result = handle_memories_by_act_page(None, act_id=act_id)

        assert page_result["memories_page_id"] == ensure_result["page_id"]
