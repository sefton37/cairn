"""Tests for StateBriefingService and briefing RPC handlers.

Covers:
- Basic generation via mocked LLM
- Cache hit within 24 hours
- Cache miss (stale briefing triggers regeneration)
- Empty knowledge base (no memories, scenes, threads)
- Persistence to state_briefings table
- RPC handler: get (cache)
- RPC handler: generate (force)
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from cairn.play_db import _get_connection, close_connection, init_db
from cairn.services.state_briefing_service import StateBriefing, StateBriefingService


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture()
def briefing_db(tmp_path):
    """Fresh DB for each test."""
    os.environ["REOS_DATA_DIR"] = str(tmp_path)
    init_db()
    yield tmp_path
    close_connection()
    os.environ.pop("REOS_DATA_DIR", None)


def _mock_provider(content: str = "You are working on a great project.") -> MagicMock:
    """Return a provider mock whose chat_text() returns the given content."""
    provider = MagicMock()
    provider.chat_text.return_value = content
    return provider


# =============================================================================
# TestGenerate
# =============================================================================


class TestGenerate:
    """StateBriefingService.generate() correctness."""

    def test_generate_produces_briefing(self, briefing_db):
        """Mock LLM — output is a non-empty StateBriefing with expected fields."""
        llm_content = "## Orientation\nYou were building the NOL bridge integration."
        service = StateBriefingService(provider=_mock_provider(llm_content))

        briefing = service.generate(trigger="new_conversation")

        assert isinstance(briefing, StateBriefing)
        assert briefing.id  # non-empty ID
        assert briefing.content == llm_content
        assert briefing.trigger == "new_conversation"
        assert briefing.generated_at  # ISO timestamp present
        assert briefing.token_count is not None and briefing.token_count > 0

    def test_generate_uses_app_start_trigger(self, briefing_db):
        service = StateBriefingService(provider=_mock_provider("Hello"))
        briefing = service.generate(trigger="app_start")
        assert briefing.trigger == "app_start"

    def test_generate_uses_manual_trigger(self, briefing_db):
        service = StateBriefingService(provider=_mock_provider("Hello"))
        briefing = service.generate(trigger="manual")
        assert briefing.trigger == "manual"

    def test_generate_token_count_approximate(self, briefing_db):
        """Token count should be roughly len(content) // 4."""
        content = "x" * 400  # 400 chars → ~100 tokens
        service = StateBriefingService(provider=_mock_provider(content))
        briefing = service.generate()
        assert briefing.token_count == 100

    def test_empty_knowledge_base_no_crash(self, briefing_db):
        """With no memories, scenes, or threads the service must not raise."""
        service = StateBriefingService(provider=_mock_provider("(Nothing to report.)"))
        briefing = service.generate()
        assert briefing.content  # Something was produced
        assert briefing.id

    def test_llm_failure_produces_fallback_briefing(self, briefing_db):
        """When the LLM raises, a minimal briefing is built without crashing."""
        provider = MagicMock()
        provider.chat_text.side_effect = RuntimeError("Ollama offline")

        # Store an approved memory via the ConversationService so FK constraints
        # are satisfied automatically.
        from cairn.services.conversation_service import ConversationService
        from cairn.services.memory_service import MemoryService

        cs = ConversationService()
        conv = cs.start()

        ms = MemoryService(
            provider=MagicMock(chat_json=MagicMock(return_value='{"is_match":false,"reason":"","merged_narrative":""}')),
            embedding_service=MagicMock(embed=MagicMock(return_value=None), find_similar=MagicMock(return_value=[])),
        )
        mem = ms.store(conv.id, "SQLite is reliable.", source="compression")
        # Approve directly so _get_top_memories() returns it
        ms.approve(mem.id)

        service = StateBriefingService(provider=provider)
        briefing = service.generate()
        assert briefing.content  # fallback content not empty
        assert "LLM unavailable" in briefing.content or "SQLite" in briefing.content


# =============================================================================
# TestPersistence
# =============================================================================


class TestPersistence:
    """Briefing rows are written to state_briefings table."""

    def test_briefing_persisted(self, briefing_db):
        """After generate(), the row exists in state_briefings."""
        service = StateBriefingService(provider=_mock_provider("Orientation text"))
        briefing = service.generate()

        conn = _get_connection()
        cursor = conn.execute(
            "SELECT * FROM state_briefings WHERE id = ?", (briefing.id,)
        )
        row = cursor.fetchone()
        assert row is not None
        assert row["content"] == "Orientation text"
        assert row["trigger"] == "new_conversation"

    def test_multiple_briefings_accumulate(self, briefing_db):
        """Each call to generate() inserts a new row (no upsert behaviour)."""
        service = StateBriefingService(provider=_mock_provider("A"))
        b1 = service.generate()
        b2 = service.generate()
        assert b1.id != b2.id

        conn = _get_connection()
        cursor = conn.execute("SELECT COUNT(*) FROM state_briefings")
        assert cursor.fetchone()[0] == 2


# =============================================================================
# TestCaching
# =============================================================================


class TestCaching:
    """get_current() and get_or_generate() cache semantics."""

    def test_get_current_returns_none_when_empty(self, briefing_db):
        service = StateBriefingService(provider=_mock_provider())
        assert service.get_current() is None

    def test_get_current_returns_fresh_briefing(self, briefing_db):
        service = StateBriefingService(provider=_mock_provider("Hello"))
        generated = service.generate()

        current = service.get_current()
        assert current is not None
        assert current.id == generated.id

    def test_get_current_returns_none_for_stale_briefing(self, briefing_db):
        """A briefing older than 24 hours is treated as stale."""
        stale_ts = (datetime.now(UTC) - timedelta(hours=25)).isoformat()
        from cairn.play_db import _transaction
        with _transaction() as conn:
            conn.execute(
                """INSERT INTO state_briefings (id, generated_at, content, token_count, trigger)
                   VALUES ('stale01', ?, 'Old content', 10, 'manual')""",
                (stale_ts,),
            )

        service = StateBriefingService(provider=_mock_provider())
        assert service.get_current() is None

    def test_get_or_generate_returns_cached(self, briefing_db):
        """Two calls within 24 h return the same briefing ID."""
        service = StateBriefingService(provider=_mock_provider("Cached"))
        b1 = service.get_or_generate()
        b2 = service.get_or_generate()
        assert b1.id == b2.id
        # Provider was called exactly once (cached on second call)
        assert service._provider.chat_text.call_count == 1

    def test_get_or_generate_regenerates_stale(self, briefing_db):
        """If the stored briefing is stale, get_or_generate() generates a new one."""
        stale_ts = (datetime.now(UTC) - timedelta(hours=25)).isoformat()
        from cairn.play_db import _transaction
        with _transaction() as conn:
            conn.execute(
                """INSERT INTO state_briefings (id, generated_at, content, token_count, trigger)
                   VALUES ('stale02', ?, 'Stale content', 10, 'manual')""",
                (stale_ts,),
            )

        service = StateBriefingService(provider=_mock_provider("Fresh content"))
        briefing = service.get_or_generate()
        assert briefing.id != "stale02"
        assert briefing.content == "Fresh content"

    def test_get_or_generate_fresh_briefing_not_regenerated(self, briefing_db):
        """A briefing 1 hour old is fresh and should not trigger regeneration."""
        fresh_ts = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        from cairn.play_db import _transaction
        with _transaction() as conn:
            conn.execute(
                """INSERT INTO state_briefings (id, generated_at, content, token_count, trigger)
                   VALUES ('fresh01', ?, 'Fresh old content', 10, 'new_conversation')""",
                (fresh_ts,),
            )

        provider = _mock_provider("Should not be called")
        service = StateBriefingService(provider=provider)
        briefing = service.get_or_generate()

        assert briefing.id == "fresh01"
        provider.chat_text.assert_not_called()


# =============================================================================
# TestRpcHandlers
# =============================================================================


class TestRpcHandlers:
    """RPC handler wiring."""

    def test_rpc_get_handler_returns_none_when_no_briefing(self, briefing_db):
        """handle_briefing_get returns {'briefing': None} when cache is empty."""
        from cairn.rpc_handlers.briefing import handle_briefing_get

        # Reset singleton so it uses the fresh test DB
        import cairn.rpc_handlers.briefing as bmod
        bmod._service = None

        result = handle_briefing_get(db=MagicMock())
        assert result == {"briefing": None}

    def test_rpc_get_handler_returns_cached_briefing(self, briefing_db):
        """handle_briefing_get returns the cached briefing dict."""
        from cairn.play_db import _transaction
        fresh_ts = datetime.now(UTC).isoformat()
        with _transaction() as conn:
            conn.execute(
                """INSERT INTO state_briefings (id, generated_at, content, token_count, trigger)
                   VALUES ('rpc001', ?, 'RPC cached content', 15, 'manual')""",
                (fresh_ts,),
            )

        from cairn.rpc_handlers.briefing import handle_briefing_get
        import cairn.rpc_handlers.briefing as bmod
        bmod._service = None

        result = handle_briefing_get(db=MagicMock())
        assert result["briefing"] is not None
        assert result["briefing"]["id"] == "rpc001"
        assert result["briefing"]["content"] == "RPC cached content"

    def test_rpc_generate_handler_creates_briefing(self, briefing_db):
        """handle_briefing_generate calls generate() and returns the new briefing."""
        from cairn.rpc_handlers.briefing import handle_briefing_generate
        import cairn.rpc_handlers.briefing as bmod

        mock_service = MagicMock()
        mock_service.generate.return_value = StateBriefing(
            id="gen001",
            content="Generated now",
            token_count=5,
            trigger="manual",
            generated_at=datetime.now(UTC).isoformat(),
        )
        bmod._service = mock_service

        result = handle_briefing_generate(db=MagicMock(), trigger="manual")
        assert result["briefing"]["id"] == "gen001"
        mock_service.generate.assert_called_once_with(trigger="manual")

    def test_rpc_generate_handler_default_trigger(self, briefing_db):
        """handle_briefing_generate uses 'manual' trigger by default."""
        from cairn.rpc_handlers.briefing import handle_briefing_generate
        import cairn.rpc_handlers.briefing as bmod

        mock_service = MagicMock()
        mock_service.generate.return_value = StateBriefing(
            id="gen002",
            content="Default trigger",
            token_count=3,
            trigger="manual",
            generated_at=datetime.now(UTC).isoformat(),
        )
        bmod._service = mock_service

        handle_briefing_generate(db=MagicMock())
        mock_service.generate.assert_called_once_with(trigger="manual")
