"""Tests for attention priorities — drag-reorder with priority learning.

Covers:
- v14 schema migration (attention_priorities table, system-signals conversation)
- get/set_attention_priorities query functions
- Surfacing algorithm respects user priority within urgency tiers
- PrioritySignalService persistence (no memory creation)
- RPC handler wiring
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Create isolated data directory for play_db."""
    data_dir = tmp_path / "reos-data"
    data_dir.mkdir()
    monkeypatch.setenv("REOS_DATA_DIR", str(data_dir))

    import cairn.play_db as play_db

    play_db.close_connection()

    yield data_dir

    play_db.close_connection()


@pytest.fixture
def initialized_db(temp_data_dir: Path):
    """Initialize the database and return the module."""
    import cairn.play_db as play_db

    play_db.init_db()
    return play_db


# =============================================================================
# Schema v14 Migration
# =============================================================================


class TestSchemaV14Migration:
    """Test v14 migration creates attention_priorities and system-signals."""

    def test_attention_priorities_table_exists(self, initialized_db) -> None:
        conn = initialized_db._get_connection()
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='attention_priorities'"
        )
        assert cursor.fetchone() is not None

    def test_attention_priorities_columns(self, initialized_db) -> None:
        conn = initialized_db._get_connection()
        cursor = conn.execute("PRAGMA table_info(attention_priorities)")
        columns = {row[1] for row in cursor.fetchall()}
        assert "scene_id" in columns
        assert "user_priority" in columns
        assert "updated_at" in columns

    def test_system_signals_conversation_exists(self, initialized_db) -> None:
        conn = initialized_db._get_connection()
        cursor = conn.execute(
            "SELECT id, status FROM conversations WHERE id = ?",
            (initialized_db.SYSTEM_SIGNALS_CONVERSATION_ID,),
        )
        row = cursor.fetchone()
        assert row is not None
        assert row["status"] == "archived"

    def test_system_signals_block_exists(self, initialized_db) -> None:
        conn = initialized_db._get_connection()
        cursor = conn.execute(
            "SELECT id, type FROM blocks WHERE id = 'block-system-signals'"
        )
        row = cursor.fetchone()
        assert row is not None
        assert row["type"] == "conversation"

    def test_schema_version_is_14(self, initialized_db) -> None:
        conn = initialized_db._get_connection()
        cursor = conn.execute("SELECT version FROM schema_version")
        assert cursor.fetchone()[0] == 14

    def test_migration_idempotent(self, initialized_db) -> None:
        """Running migration again should not fail."""
        conn = initialized_db._get_connection()
        from cairn.play_db import _migrate_v13_to_v14

        _migrate_v13_to_v14(conn)  # Should not raise


# =============================================================================
# Attention Priority Storage
# =============================================================================


class TestAttentionPriorityStorage:
    """Test get/set_attention_priorities functions."""

    def test_empty_priorities(self, initialized_db) -> None:
        result = initialized_db.get_attention_priorities()
        assert result == {}

    def test_set_and_get_priorities(self, initialized_db) -> None:
        # Create some scenes to reference
        conn = initialized_db._get_connection()
        _create_test_scene(conn, "scene-a", "act-1", "Scene A")
        _create_test_scene(conn, "scene-b", "act-1", "Scene B")
        _create_test_scene(conn, "scene-c", "act-1", "Scene C")

        initialized_db.set_attention_priorities(["scene-c", "scene-a", "scene-b"])

        result = initialized_db.get_attention_priorities()
        assert result == {"scene-c": 0, "scene-a": 1, "scene-b": 2}

    def test_set_overwrites_previous(self, initialized_db) -> None:
        conn = initialized_db._get_connection()
        _create_test_scene(conn, "scene-x", "act-1", "X")
        _create_test_scene(conn, "scene-y", "act-1", "Y")

        initialized_db.set_attention_priorities(["scene-x", "scene-y"])
        initialized_db.set_attention_priorities(["scene-y", "scene-x"])

        result = initialized_db.get_attention_priorities()
        assert result["scene-y"] == 0
        assert result["scene-x"] == 1

    def test_set_empty_list_clears(self, initialized_db) -> None:
        conn = initialized_db._get_connection()
        _create_test_scene(conn, "scene-z", "act-1", "Z")

        initialized_db.set_attention_priorities(["scene-z"])
        assert len(initialized_db.get_attention_priorities()) == 1

        initialized_db.set_attention_priorities([])
        assert initialized_db.get_attention_priorities() == {}


# =============================================================================
# Surfacing Algorithm
# =============================================================================


class TestSurfacingWithPriority:
    """Test that _rank_and_dedupe respects user priorities."""

    def test_priority_within_urgency_tier(self, initialized_db) -> None:
        from cairn.cairn.models import SurfacedItem

        items = [
            SurfacedItem(
                entity_type="scene", entity_id="s1",
                title="First", reason="r", urgency="high",
            ),
            SurfacedItem(
                entity_type="scene", entity_id="s2",
                title="Second", reason="r", urgency="high",
            ),
            SurfacedItem(
                entity_type="scene", entity_id="s3",
                title="Third", reason="r", urgency="high",
            ),
        ]

        # Set s3 as highest priority, then s1
        conn = initialized_db._get_connection()
        _create_test_scene(conn, "s3", "act-1", "Third")
        _create_test_scene(conn, "s1", "act-1", "First")
        initialized_db.set_attention_priorities(["s3", "s1"])

        from cairn.cairn.surfacing import CairnSurfacer

        surfacer = CairnSurfacer.__new__(CairnSurfacer)
        result = surfacer._rank_and_dedupe(items, max_items=10)

        # s3 should be first (priority 0), s1 second (priority 1), s2 last (no priority)
        assert result[0].entity_id == "s3"
        assert result[1].entity_id == "s1"
        assert result[2].entity_id == "s2"

    def test_urgency_still_takes_precedence(self, initialized_db) -> None:
        from cairn.cairn.models import SurfacedItem

        items = [
            SurfacedItem(
                entity_type="scene", entity_id="low-pri",
                title="Low", reason="r", urgency="low",
            ),
            SurfacedItem(
                entity_type="scene", entity_id="critical",
                title="Critical", reason="r", urgency="critical",
            ),
        ]

        # User prioritized low item
        conn = initialized_db._get_connection()
        _create_test_scene(conn, "low-pri", "act-1", "Low")
        initialized_db.set_attention_priorities(["low-pri"])

        from cairn.cairn.surfacing import CairnSurfacer

        surfacer = CairnSurfacer.__new__(CairnSurfacer)
        result = surfacer._rank_and_dedupe(items, max_items=10)

        # Critical urgency still comes first despite user priority
        assert result[0].entity_id == "critical"
        assert result[1].entity_id == "low-pri"

    def test_user_priority_attached_to_items(self, initialized_db) -> None:
        from cairn.cairn.models import SurfacedItem

        items = [
            SurfacedItem(
                entity_type="scene", entity_id="s1",
                title="One", reason="r", urgency="medium",
            ),
        ]

        conn = initialized_db._get_connection()
        _create_test_scene(conn, "s1", "act-1", "One")
        initialized_db.set_attention_priorities(["s1"])

        from cairn.cairn.surfacing import CairnSurfacer

        surfacer = CairnSurfacer.__new__(CairnSurfacer)
        result = surfacer._rank_and_dedupe(items, max_items=10)

        assert result[0].user_priority == 0


# =============================================================================
# PrioritySignalService
# =============================================================================


class TestPrioritySignalService:
    """Test PrioritySignalService.process_reorder (persistence only)."""

    def test_process_reorder_persists_priorities(self, initialized_db) -> None:
        conn = initialized_db._get_connection()
        _create_test_scene(conn, "sa", "act-1", "Alpha")
        _create_test_scene(conn, "sb", "act-1", "Beta")

        from cairn.services.priority_signal_service import PrioritySignalService

        service = PrioritySignalService()
        result = service.process_reorder(ordered_scene_ids=["sb", "sa"])

        assert result["priorities_updated"] == 2
        assert "memory_id" not in result

        priorities = initialized_db.get_attention_priorities()
        assert priorities["sb"] == 0
        assert priorities["sa"] == 1

    def test_process_reorder_empty_list(self, initialized_db) -> None:
        from cairn.services.priority_signal_service import PrioritySignalService

        service = PrioritySignalService()
        result = service.process_reorder(ordered_scene_ids=[])

        assert result["priorities_updated"] == 0
        assert "memory_id" not in result

    def test_no_memory_service_dependency(self) -> None:
        """PrioritySignalService should not depend on MemoryService."""
        import inspect
        from cairn.services.priority_signal_service import PrioritySignalService

        sig = inspect.signature(PrioritySignalService.__init__)
        param_names = list(sig.parameters.keys())
        assert "memory_service" not in param_names

        sig = inspect.signature(PrioritySignalService.process_reorder)
        param_names = list(sig.parameters.keys())
        assert "scene_titles" not in param_names


# =============================================================================
# State Briefing Integration
# =============================================================================


class TestStateBriefingPriorities:
    """Test that state briefing includes attention priorities."""

    def test_get_attention_priorities_method(self, initialized_db) -> None:
        conn = initialized_db._get_connection()
        _create_test_scene(conn, "s1", "act-1", "Important Scene")
        _create_test_scene(conn, "s2", "act-1", "Less Important")
        initialized_db.set_attention_priorities(["s1", "s2"])

        from cairn.services.state_briefing_service import StateBriefingService

        service = StateBriefingService.__new__(StateBriefingService)
        result = service._get_attention_priorities(limit=5)

        assert len(result) == 2
        assert result[0] == "#1: Important Scene"
        assert result[1] == "#2: Less Important"

    def test_get_attention_priorities_empty(self, initialized_db) -> None:
        from cairn.services.state_briefing_service import StateBriefingService

        service = StateBriefingService.__new__(StateBriefingService)
        result = service._get_attention_priorities()
        assert result == []


# =============================================================================
# Helpers
# =============================================================================


def _create_test_scene(
    conn, scene_id: str, act_id: str, title: str
) -> None:
    """Create a minimal act + scene for testing."""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()

    # Ensure act exists
    conn.execute(
        """INSERT OR IGNORE INTO acts (act_id, title, active, position, created_at, updated_at)
           VALUES (?, ?, 1, 0, ?, ?)""",
        (act_id, f"Act {act_id}", now, now),
    )

    # Create scene
    conn.execute(
        """INSERT OR IGNORE INTO scenes
           (scene_id, act_id, title, stage, position, created_at, updated_at)
           VALUES (?, ?, ?, 'planning', 0, ?, ?)""",
        (scene_id, act_id, title, now, now),
    )
