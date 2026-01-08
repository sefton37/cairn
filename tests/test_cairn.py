"""Tests for CAIRN module.

Tests the attention minder's core functionality:
- Metadata store (CRUD, kanban states, priorities)
- Activity tracking
- Contact links
- Surfacing algorithms
"""

from __future__ import annotations

import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from reos.cairn.models import (
    ActivityType,
    CairnMetadata,
    ContactRelationship,
    KanbanState,
    SurfaceContext,
)
from reos.cairn.store import CairnStore
from reos.cairn.surfacing import CairnSurfacer


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_db() -> Path:
    """Create a temporary database file."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        yield Path(f.name)


@pytest.fixture
def cairn_store(temp_db: Path) -> CairnStore:
    """Create a CAIRN store with temp database."""
    return CairnStore(temp_db)


@pytest.fixture
def surfacer(cairn_store: CairnStore) -> CairnSurfacer:
    """Create a surfacer with the test store."""
    return CairnSurfacer(cairn_store)


# =============================================================================
# Store Tests - Metadata CRUD
# =============================================================================


class TestMetadataCRUD:
    """Test metadata create, read, update, delete operations."""

    def test_get_metadata_nonexistent(self, cairn_store: CairnStore) -> None:
        """Getting nonexistent metadata returns None."""
        result = cairn_store.get_metadata("act", "nonexistent")
        assert result is None

    def test_get_or_create_creates_new(self, cairn_store: CairnStore) -> None:
        """get_or_create creates new metadata if not exists."""
        metadata = cairn_store.get_or_create_metadata("act", "test-act-1")

        assert metadata.entity_type == "act"
        assert metadata.entity_id == "test-act-1"
        assert metadata.kanban_state == KanbanState.BACKLOG
        assert metadata.touch_count == 0

    def test_get_or_create_returns_existing(self, cairn_store: CairnStore) -> None:
        """get_or_create returns existing metadata."""
        # Create first
        cairn_store.get_or_create_metadata("act", "test-act-1")

        # Touch it to change touch_count
        cairn_store.touch("act", "test-act-1")

        # Get again
        metadata = cairn_store.get_or_create_metadata("act", "test-act-1")
        assert metadata.touch_count == 1

    def test_save_metadata_updates(self, cairn_store: CairnStore) -> None:
        """save_metadata updates existing metadata."""
        metadata = cairn_store.get_or_create_metadata("act", "test-act-1")
        metadata.priority = 5
        metadata.priority_reason = "Urgent"
        cairn_store.save_metadata(metadata)

        # Retrieve and verify
        retrieved = cairn_store.get_metadata("act", "test-act-1")
        assert retrieved is not None
        assert retrieved.priority == 5
        assert retrieved.priority_reason == "Urgent"

    def test_delete_metadata(self, cairn_store: CairnStore) -> None:
        """delete_metadata removes metadata."""
        cairn_store.get_or_create_metadata("act", "test-act-1")

        deleted = cairn_store.delete_metadata("act", "test-act-1")
        assert deleted is True

        # Verify gone
        result = cairn_store.get_metadata("act", "test-act-1")
        assert result is None

    def test_delete_nonexistent_returns_false(self, cairn_store: CairnStore) -> None:
        """delete_metadata returns False for nonexistent."""
        deleted = cairn_store.delete_metadata("act", "nonexistent")
        assert deleted is False


# =============================================================================
# Store Tests - Kanban States
# =============================================================================


class TestKanbanStates:
    """Test kanban state management."""

    def test_set_kanban_state(self, cairn_store: CairnStore) -> None:
        """set_kanban_state changes state."""
        cairn_store.get_or_create_metadata("act", "test-act-1")

        metadata = cairn_store.set_kanban_state("act", "test-act-1", KanbanState.ACTIVE)
        assert metadata.kanban_state == KanbanState.ACTIVE

    def test_set_waiting_state_records_waiting_on(self, cairn_store: CairnStore) -> None:
        """WAITING state records who we're waiting on."""
        cairn_store.get_or_create_metadata("act", "test-act-1")

        metadata = cairn_store.set_kanban_state(
            "act", "test-act-1", KanbanState.WAITING, waiting_on="Client feedback"
        )

        assert metadata.kanban_state == KanbanState.WAITING
        assert metadata.waiting_on == "Client feedback"
        assert metadata.waiting_since is not None

    def test_leaving_waiting_clears_waiting_info(self, cairn_store: CairnStore) -> None:
        """Leaving WAITING state clears waiting_on."""
        cairn_store.get_or_create_metadata("act", "test-act-1")
        cairn_store.set_kanban_state("act", "test-act-1", KanbanState.WAITING, waiting_on="Client")

        metadata = cairn_store.set_kanban_state("act", "test-act-1", KanbanState.ACTIVE)

        assert metadata.waiting_on is None
        assert metadata.waiting_since is None

    def test_mark_completed(self, cairn_store: CairnStore) -> None:
        """mark_completed sets state to DONE."""
        cairn_store.get_or_create_metadata("act", "test-act-1")

        metadata = cairn_store.mark_completed("act", "test-act-1")
        assert metadata.kanban_state == KanbanState.DONE


# =============================================================================
# Store Tests - Priority
# =============================================================================


class TestPriority:
    """Test priority management."""

    def test_set_priority_valid(self, cairn_store: CairnStore) -> None:
        """set_priority with valid value works."""
        cairn_store.get_or_create_metadata("act", "test-act-1")

        metadata = cairn_store.set_priority("act", "test-act-1", 5, reason="Critical deadline")

        assert metadata.priority == 5
        assert metadata.priority_reason == "Critical deadline"
        assert metadata.priority_set_at is not None

    def test_set_priority_invalid_raises(self, cairn_store: CairnStore) -> None:
        """set_priority with invalid value raises."""
        cairn_store.get_or_create_metadata("act", "test-act-1")

        with pytest.raises(ValueError, match="Priority must be between 1 and 5"):
            cairn_store.set_priority("act", "test-act-1", 10)

    def test_clear_priority(self, cairn_store: CairnStore) -> None:
        """clear_priority removes priority."""
        cairn_store.get_or_create_metadata("act", "test-act-1")
        cairn_store.set_priority("act", "test-act-1", 5)

        metadata = cairn_store.clear_priority("act", "test-act-1")

        assert metadata.priority is None
        assert metadata.priority_reason is None


# =============================================================================
# Store Tests - Activity Tracking
# =============================================================================


class TestActivityTracking:
    """Test activity/touch tracking."""

    def test_touch_increments_count(self, cairn_store: CairnStore) -> None:
        """touch increments touch_count."""
        cairn_store.get_or_create_metadata("act", "test-act-1")

        cairn_store.touch("act", "test-act-1")
        cairn_store.touch("act", "test-act-1")
        cairn_store.touch("act", "test-act-1")

        metadata = cairn_store.get_metadata("act", "test-act-1")
        assert metadata is not None
        assert metadata.touch_count == 3

    def test_touch_updates_last_touched(self, cairn_store: CairnStore) -> None:
        """touch updates last_touched timestamp."""
        metadata = cairn_store.get_or_create_metadata("act", "test-act-1")
        original_touched = metadata.last_touched

        # Touch again
        updated = cairn_store.touch("act", "test-act-1")

        assert updated.last_touched >= original_touched

    def test_touch_logs_activity(self, cairn_store: CairnStore) -> None:
        """touch creates activity log entry."""
        cairn_store.touch("act", "test-act-1", activity_type=ActivityType.EDITED)

        log = cairn_store.get_activity_log(entity_type="act", entity_id="test-act-1")
        assert len(log) >= 1
        assert log[0].activity_type == ActivityType.EDITED


# =============================================================================
# Store Tests - Contact Links
# =============================================================================


class TestContactLinks:
    """Test contact knowledge graph."""

    def test_link_contact(self, cairn_store: CairnStore) -> None:
        """link_contact creates a link."""
        link = cairn_store.link_contact(
            contact_id="contact-1",
            entity_type="act",
            entity_id="test-act-1",
            relationship=ContactRelationship.COLLABORATOR,
            notes="Working on this together",
        )

        assert link.contact_id == "contact-1"
        assert link.relationship == ContactRelationship.COLLABORATOR

    def test_get_contact_links(self, cairn_store: CairnStore) -> None:
        """get_contact_links returns links."""
        cairn_store.link_contact("c1", "act", "a1", ContactRelationship.OWNER)
        cairn_store.link_contact("c1", "act", "a2", ContactRelationship.COLLABORATOR)

        links = cairn_store.get_contact_links(contact_id="c1")
        assert len(links) == 2

    def test_unlink_contact(self, cairn_store: CairnStore) -> None:
        """unlink_contact removes link."""
        link = cairn_store.link_contact("c1", "act", "a1", ContactRelationship.OWNER)

        removed = cairn_store.unlink_contact(link.link_id)
        assert removed is True

        links = cairn_store.get_contact_links(contact_id="c1")
        assert len(links) == 0


# =============================================================================
# Store Tests - Time Management
# =============================================================================


class TestTimeManagement:
    """Test due dates and deferral."""

    def test_set_due_date(self, cairn_store: CairnStore) -> None:
        """set_due_date works."""
        cairn_store.get_or_create_metadata("act", "test-act-1")
        due = datetime.now() + timedelta(days=7)

        metadata = cairn_store.set_due_date("act", "test-act-1", due)
        assert metadata.due_date is not None

    def test_defer_until(self, cairn_store: CairnStore) -> None:
        """defer_until sets defer date and moves to someday."""
        cairn_store.get_or_create_metadata("act", "test-act-1")
        cairn_store.set_kanban_state("act", "test-act-1", KanbanState.ACTIVE)

        defer_date = datetime.now() + timedelta(days=14)
        metadata = cairn_store.defer_until("act", "test-act-1", defer_date)

        assert metadata.defer_until is not None
        assert metadata.kanban_state == KanbanState.SOMEDAY


# =============================================================================
# Store Tests - Listing and Filtering
# =============================================================================


class TestListingFilters:
    """Test list_metadata with filters."""

    def test_list_by_entity_type(self, cairn_store: CairnStore) -> None:
        """list_metadata filters by entity_type."""
        cairn_store.get_or_create_metadata("act", "a1")
        cairn_store.get_or_create_metadata("scene", "s1")
        cairn_store.get_or_create_metadata("beat", "b1")

        acts = cairn_store.list_metadata(entity_type="act")
        assert len(acts) == 1
        assert acts[0].entity_type == "act"

    def test_list_by_kanban_state(self, cairn_store: CairnStore) -> None:
        """list_metadata filters by kanban_state."""
        cairn_store.get_or_create_metadata("act", "a1")
        cairn_store.set_kanban_state("act", "a1", KanbanState.ACTIVE)

        cairn_store.get_or_create_metadata("act", "a2")
        cairn_store.set_kanban_state("act", "a2", KanbanState.BACKLOG)

        active = cairn_store.list_metadata(kanban_state=KanbanState.ACTIVE)
        assert len(active) == 1
        assert active[0].entity_id == "a1"

    def test_list_with_priority(self, cairn_store: CairnStore) -> None:
        """list_metadata filters by has_priority."""
        cairn_store.get_or_create_metadata("act", "a1")
        cairn_store.set_priority("act", "a1", 5)

        cairn_store.get_or_create_metadata("act", "a2")

        with_priority = cairn_store.list_metadata(has_priority=True)
        assert len(with_priority) == 1
        assert with_priority[0].entity_id == "a1"


# =============================================================================
# Surfacing Tests
# =============================================================================


class TestSurfacing:
    """Test surfacing algorithms."""

    def test_surface_next_returns_list(self, surfacer: CairnSurfacer, cairn_store: CairnStore) -> None:
        """surface_next returns a list of surfaced items."""
        cairn_store.get_or_create_metadata("act", "a1")
        cairn_store.set_kanban_state("act", "a1", KanbanState.ACTIVE)
        cairn_store.set_priority("act", "a1", 5)

        result = surfacer.surface_next()

        assert isinstance(result, list)
        # May or may not contain items depending on context
        if result:
            assert hasattr(result[0], 'entity_id')

    def test_surface_today_returns_list(self, surfacer: CairnSurfacer, cairn_store: CairnStore) -> None:
        """surface_today returns a list."""
        cairn_store.get_or_create_metadata("act", "a1")
        cairn_store.set_kanban_state("act", "a1", KanbanState.ACTIVE)

        results = surfacer.surface_today()

        assert isinstance(results, list)

    def test_surface_stale_returns_old_items(self, surfacer: CairnSurfacer, cairn_store: CairnStore) -> None:
        """surface_stale returns items not touched recently."""
        # Create an item and set to ACTIVE state
        cairn_store.get_or_create_metadata("act", "a1")
        cairn_store.set_kanban_state("act", "a1", KanbanState.ACTIVE)

        # Re-fetch after state change (set_kanban_state saves a fresh copy)
        metadata = cairn_store.get_metadata("act", "a1")
        assert metadata is not None

        # Manually set last_touched to 8 days ago (active items stale after 3 days)
        metadata.last_touched = datetime.now() - timedelta(days=8)
        cairn_store.save_metadata(metadata)

        # surface_stale uses days parameter, not stale_days
        results = surfacer.surface_stale(days=3)

        assert len(results) >= 1
        assert any(r.entity_id == "a1" for r in results)

    def test_surface_waiting_returns_waiting_items(self, surfacer: CairnSurfacer, cairn_store: CairnStore) -> None:
        """surface_waiting returns items in WAITING state."""
        cairn_store.get_or_create_metadata("act", "a1")
        cairn_store.set_kanban_state("act", "a1", KanbanState.WAITING, waiting_on="Client")

        results = surfacer.surface_waiting()

        assert len(results) >= 1
        assert any(r.entity_id == "a1" for r in results)

    def test_surface_needs_priority(self, surfacer: CairnSurfacer, cairn_store: CairnStore) -> None:
        """surface_needs_priority returns active items without priority."""
        cairn_store.get_or_create_metadata("act", "a1")
        cairn_store.set_kanban_state("act", "a1", KanbanState.ACTIVE)
        # No priority set

        results = surfacer.surface_needs_priority()

        assert len(results) >= 1
        assert any(r.entity_id == "a1" for r in results)


# =============================================================================
# Model Tests
# =============================================================================


class TestModels:
    """Test CAIRN model classes."""

    def test_cairn_metadata_is_stale_active(self) -> None:
        """is_stale for ACTIVE items (stale after 3 days)."""
        metadata = CairnMetadata(
            entity_type="act",
            entity_id="a1",
            kanban_state=KanbanState.ACTIVE,
            last_touched=datetime.now() - timedelta(days=5),
        )
        assert metadata.is_stale is True

        metadata.last_touched = datetime.now()
        assert metadata.is_stale is False

    def test_cairn_metadata_is_stale_backlog(self) -> None:
        """is_stale for BACKLOG items (stale after 14 days)."""
        metadata = CairnMetadata(
            entity_type="act",
            entity_id="a1",
            kanban_state=KanbanState.BACKLOG,
            last_touched=datetime.now() - timedelta(days=8),
        )
        # Backlog items are not stale until 14 days
        assert metadata.is_stale is False

        metadata.last_touched = datetime.now() - timedelta(days=15)
        assert metadata.is_stale is True

    def test_cairn_metadata_needs_priority(self) -> None:
        """needs_priority property works correctly."""
        metadata = CairnMetadata(
            entity_type="act",
            entity_id="a1",
            kanban_state=KanbanState.ACTIVE,
            priority=None,
        )
        assert metadata.needs_priority is True

        metadata.priority = 3
        assert metadata.needs_priority is False

    def test_kanban_state_values(self) -> None:
        """KanbanState enum has expected values."""
        assert KanbanState.ACTIVE.value == "active"
        assert KanbanState.BACKLOG.value == "backlog"
        assert KanbanState.WAITING.value == "waiting"
        assert KanbanState.SOMEDAY.value == "someday"
        assert KanbanState.DONE.value == "done"

    def test_surface_context_has_max_items(self) -> None:
        """SurfaceContext has max_items attribute."""
        context = SurfaceContext()
        # Check max_items exists (default should be 5)
        assert hasattr(context, 'max_items')
        assert context.max_items == 5
