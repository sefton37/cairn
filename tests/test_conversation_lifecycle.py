"""Tests for conversation lifecycle service.

Tests the ConversationService: singleton enforcement, state machine
transitions, message handling, and block integration.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def conv_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Set up a fresh play database for conversation tests."""
    data_dir = tmp_path / "reos-data"
    data_dir.mkdir()
    monkeypatch.setenv("REOS_DATA_DIR", str(data_dir))

    import cairn.play_db as play_db

    play_db.close_connection()
    play_db.init_db()

    yield data_dir

    play_db.close_connection()


@pytest.fixture
def service(conv_db):
    """Get a ConversationService with fresh database."""
    from cairn.services.conversation_service import ConversationService

    return ConversationService()


# =============================================================================
# Singleton Constraint
# =============================================================================


class TestConversationSingleton:
    """Tests for the one-active-conversation constraint."""

    def test_start_first_conversation(self, service):
        """Starting a conversation when none exists returns an active conversation."""
        from cairn.services.conversation_service import ConversationService

        conv = service.start()

        assert conv.status == "active"
        assert conv.message_count == 0
        assert conv.id is not None
        assert conv.block_id is not None

    def test_singleton_enforcement(self, service):
        """Starting a second conversation while one is active raises ConversationError."""
        from cairn.services.conversation_service import ConversationError

        service.start()

        with pytest.raises(ConversationError, match="active"):
            service.start()

    def test_can_start_after_archiving_previous(self, service):
        """A new conversation can be started once the previous is fully archived."""
        conv1 = service.start()
        service.close(conv1.id)
        service.start_compression(conv1.id)
        service.archive(conv1.id)

        conv2 = service.start()

        assert conv2.id != conv1.id
        assert conv2.status == "active"

    def test_get_active_returns_none_when_empty(self, service):
        """get_active returns None when no conversation has been started."""
        assert service.get_active() is None

    def test_get_active_returns_active_conversation(self, service):
        """get_active returns the current active conversation by ID."""
        conv = service.start()

        active = service.get_active()

        assert active is not None
        assert active.id == conv.id

    def test_get_active_returns_none_after_close(self, service):
        """get_active returns None once the conversation is closed."""
        conv = service.start()
        service.close(conv.id)

        assert service.get_active() is None

    def test_second_start_does_not_create_orphan(self, service):
        """A rejected start() call must not persist a partial conversation row."""
        from cairn.services.conversation_service import ConversationError

        service.start()

        with pytest.raises(ConversationError):
            service.start()

        # Only the original active conversation exists
        all_convs = service.list_conversations()
        assert len(all_convs) == 1


# =============================================================================
# State Machine Transitions
# =============================================================================


class TestStateTransitions:
    """Tests for the conversation state machine."""

    def test_close_active_conversation(self, service):
        """close() transitions an active conversation to ready_to_close."""
        conv = service.start()

        closed = service.close(conv.id)

        assert closed.status == "ready_to_close"

    def test_resume_from_ready_to_close(self, service):
        """resume() transitions a ready_to_close conversation back to active."""
        conv = service.start()
        service.close(conv.id)

        resumed = service.resume(conv.id)

        assert resumed.status == "active"

    def test_compression_from_ready_to_close(self, service):
        """start_compression() transitions ready_to_close to compressing."""
        conv = service.start()
        service.close(conv.id)

        compressing = service.start_compression(conv.id)

        assert compressing.status == "compressing"

    def test_archive_from_compressing(self, service):
        """archive() transitions a compressing conversation to archived."""
        conv = service.start()
        service.close(conv.id)
        service.start_compression(conv.id)

        archived = service.archive(conv.id)

        assert archived.status == "archived"

    def test_fail_compression_rolls_back_to_ready_to_close(self, service):
        """fail_compression() rolls a compressing conversation back to ready_to_close."""
        conv = service.start()
        service.close(conv.id)
        service.start_compression(conv.id)

        failed = service.fail_compression(conv.id)

        assert failed.status == "ready_to_close"

    def test_cannot_close_archived_conversation(self, service):
        """close() on an archived conversation raises ConversationError."""
        from cairn.services.conversation_service import ConversationError

        conv = service.start()
        service.close(conv.id)
        service.start_compression(conv.id)
        service.archive(conv.id)

        with pytest.raises(ConversationError, match="Invalid transition"):
            service.close(conv.id)

    def test_cannot_skip_active_to_compressing(self, service):
        """start_compression() on an active conversation raises ConversationError."""
        from cairn.services.conversation_service import ConversationError

        conv = service.start()

        with pytest.raises(ConversationError, match="Invalid transition"):
            service.start_compression(conv.id)

    def test_cannot_skip_active_to_archived(self, service):
        """archive() on an active conversation raises ConversationError."""
        from cairn.services.conversation_service import ConversationError

        conv = service.start()

        with pytest.raises(ConversationError, match="Invalid transition"):
            service.archive(conv.id)

    def test_cannot_transition_nonexistent_conversation(self, service):
        """close() on an unknown ID raises ConversationError with 'not found'."""
        from cairn.services.conversation_service import ConversationError

        with pytest.raises(ConversationError, match="not found"):
            service.close("nonexistent-id")

    def test_close_sets_closed_at_timestamp(self, service):
        """close() persists closed_at timestamp on the conversation row."""
        conv = service.start()

        service.close(conv.id)
        reloaded = service.get_by_id(conv.id)

        assert reloaded is not None
        assert reloaded.closed_at is not None

    def test_archive_sets_archived_at_timestamp(self, service):
        """archive() persists archived_at timestamp on the conversation row."""
        conv = service.start()
        service.close(conv.id)
        service.start_compression(conv.id)

        service.archive(conv.id)
        reloaded = service.get_by_id(conv.id)

        assert reloaded is not None
        assert reloaded.archived_at is not None

    def test_resume_after_fail_compression(self, service):
        """A conversation rolled back from compressing can be resumed to active."""
        conv = service.start()
        service.close(conv.id)
        service.start_compression(conv.id)
        service.fail_compression(conv.id)

        resumed = service.resume(conv.id)

        assert resumed.status == "active"


# =============================================================================
# Message Handling
# =============================================================================


class TestMessages:
    """Tests for message handling within conversations."""

    def test_add_message_returns_message_with_correct_fields(self, service):
        """add_message returns a Message with role, content, position, and block_id."""
        conv = service.start()

        msg = service.add_message(conv.id, "user", "Hello")

        assert msg.role == "user"
        assert msg.content == "Hello"
        assert msg.position == 0
        assert msg.block_id is not None

    def test_message_position_increments_sequentially(self, service):
        """Messages within a conversation are assigned sequential positions."""
        conv = service.start()

        service.add_message(conv.id, "user", "First")
        service.add_message(conv.id, "cairn", "Second")
        service.add_message(conv.id, "user", "Third")
        messages = service.get_messages(conv.id)

        assert len(messages) == 3
        assert messages[0].content == "First"
        assert messages[0].position == 0
        assert messages[1].content == "Second"
        assert messages[1].position == 1
        assert messages[2].content == "Third"
        assert messages[2].position == 2

    def test_add_message_increments_conversation_count(self, service):
        """Adding two messages updates message_count to 2 and sets last_message_at."""
        conv = service.start()

        service.add_message(conv.id, "user", "Hello")
        service.add_message(conv.id, "cairn", "Hi")
        updated = service.get_by_id(conv.id)

        assert updated is not None
        assert updated.message_count == 2
        assert updated.last_message_at is not None

    def test_cannot_add_message_to_ready_to_close_conversation(self, service):
        """add_message raises ConversationError when conversation is ready_to_close."""
        from cairn.services.conversation_service import ConversationError

        conv = service.start()
        service.close(conv.id)

        with pytest.raises(ConversationError, match="ready_to_close"):
            service.add_message(conv.id, "user", "Too late")

    def test_cannot_add_message_to_nonexistent_conversation(self, service):
        """add_message raises ConversationError with 'not found' for unknown IDs."""
        from cairn.services.conversation_service import ConversationError

        with pytest.raises(ConversationError, match="not found"):
            service.add_message("bad-id", "user", "Hello")

    def test_message_stores_act_and_scene_context(self, service):
        """add_message persists active_act_id and active_scene_id when provided."""
        conv = service.start()

        msg = service.add_message(
            conv.id,
            "user",
            "Hello",
            active_act_id="your-story",
            active_scene_id="scene-1",
        )

        assert msg.active_act_id == "your-story"
        assert msg.active_scene_id == "scene-1"

    def test_message_stores_null_context_when_omitted(self, service):
        """add_message stores None for act/scene context when not provided."""
        conv = service.start()

        msg = service.add_message(conv.id, "user", "Hello")

        assert msg.active_act_id is None
        assert msg.active_scene_id is None

    def test_get_messages_returns_empty_list_for_new_conversation(self, service):
        """get_messages returns an empty list when no messages have been added."""
        conv = service.start()

        messages = service.get_messages(conv.id)

        assert messages == []

    def test_get_messages_respects_conversation_isolation(self, service):
        """Messages from one conversation are not visible in another."""
        conv1 = service.start()
        service.add_message(conv1.id, "user", "In conv1")
        service.close(conv1.id)
        service.start_compression(conv1.id)
        service.archive(conv1.id)

        conv2 = service.start()
        service.add_message(conv2.id, "user", "In conv2")

        assert len(service.get_messages(conv1.id)) == 1
        assert len(service.get_messages(conv2.id)) == 1
        assert service.get_messages(conv1.id)[0].content == "In conv1"
        assert service.get_messages(conv2.id)[0].content == "In conv2"

    def test_message_conversation_id_is_set(self, service):
        """add_message sets the conversation_id field on the returned Message."""
        conv = service.start()

        msg = service.add_message(conv.id, "cairn", "Response")

        assert msg.conversation_id == conv.id

    def test_cannot_add_message_to_compressing_conversation(self, service):
        """add_message raises ConversationError when conversation is compressing."""
        from cairn.services.conversation_service import ConversationError

        conv = service.start()
        service.close(conv.id)
        service.start_compression(conv.id)

        with pytest.raises(ConversationError):
            service.add_message(conv.id, "user", "Still talking?")

    def test_cannot_add_message_to_archived_conversation(self, service):
        """add_message raises ConversationError when conversation is archived."""
        from cairn.services.conversation_service import ConversationError

        conv = service.start()
        service.close(conv.id)
        service.start_compression(conv.id)
        service.archive(conv.id)

        with pytest.raises(ConversationError):
            service.add_message(conv.id, "user", "Ghost message")


# =============================================================================
# Pause / Unpause
# =============================================================================


class TestPauseUnpause:
    """Tests for pause/unpause functionality."""

    def test_pause_active_conversation(self, service):
        """pause() sets is_paused to True on an active conversation."""
        conv = service.start()

        paused = service.pause(conv.id)

        assert paused.is_paused is True

    def test_unpause_conversation(self, service):
        """unpause() clears is_paused on a paused conversation."""
        conv = service.start()
        service.pause(conv.id)

        unpaused = service.unpause(conv.id)

        assert unpaused.is_paused is False

    def test_pause_persists_to_database(self, service):
        """Paused state is written to the database and readable via get_by_id."""
        conv = service.start()
        service.pause(conv.id)

        reloaded = service.get_by_id(conv.id)

        assert reloaded is not None
        assert reloaded.is_paused is True

    def test_unpause_persists_to_database(self, service):
        """Unpaused state is written to the database and readable via get_by_id."""
        conv = service.start()
        service.pause(conv.id)
        service.unpause(conv.id)

        reloaded = service.get_by_id(conv.id)

        assert reloaded is not None
        assert reloaded.is_paused is False

    def test_cannot_pause_ready_to_close_conversation(self, service):
        """pause() raises ConversationError when conversation is not active."""
        from cairn.services.conversation_service import ConversationError

        conv = service.start()
        service.close(conv.id)

        with pytest.raises(ConversationError, match="active"):
            service.pause(conv.id)

    def test_cannot_pause_nonexistent_conversation(self, service):
        """pause() raises ConversationError for unknown conversation IDs."""
        from cairn.services.conversation_service import ConversationError

        with pytest.raises(ConversationError, match="not found"):
            service.pause("ghost-id")


# =============================================================================
# List Conversations
# =============================================================================


class TestListConversations:
    """Tests for listing conversations."""

    def test_list_returns_empty_when_no_conversations(self, service):
        """list_conversations returns an empty list when the table is empty."""
        convs = service.list_conversations()

        assert convs == []

    def test_list_returns_all_conversations_without_filter(self, service):
        """list_conversations returns all rows when no status filter is applied."""
        conv1 = service.start()
        service.close(conv1.id)
        service.start_compression(conv1.id)
        service.archive(conv1.id)

        conv2 = service.start()
        service.close(conv2.id)

        all_convs = service.list_conversations()

        assert len(all_convs) == 2

    def test_list_by_status_archived(self, service):
        """list_conversations(status='archived') returns only archived conversations."""
        conv = service.start()
        service.close(conv.id)
        service.start_compression(conv.id)
        service.archive(conv.id)

        archived = service.list_conversations(status="archived")

        assert len(archived) == 1
        assert archived[0].id == conv.id

    def test_list_by_status_active_empty_when_none_active(self, service):
        """list_conversations(status='active') returns empty list when all are closed."""
        conv = service.start()
        service.close(conv.id)
        service.start_compression(conv.id)
        service.archive(conv.id)

        active = service.list_conversations(status="active")

        assert active == []

    def test_list_by_status_ready_to_close(self, service):
        """list_conversations(status='ready_to_close') isolates that status."""
        conv = service.start()
        service.close(conv.id)

        ready = service.list_conversations(status="ready_to_close")
        active = service.list_conversations(status="active")

        assert len(ready) == 1
        assert ready[0].id == conv.id
        assert len(active) == 0

    def test_list_returns_most_recent_first(self, service):
        """list_conversations orders conversations by started_at descending."""
        conv1 = service.start()
        service.close(conv1.id)
        service.start_compression(conv1.id)
        service.archive(conv1.id)

        conv2 = service.start()

        all_convs = service.list_conversations()

        # conv2 started later, so it should appear first
        assert all_convs[0].id == conv2.id
        assert all_convs[1].id == conv1.id


# =============================================================================
# Block Integration
# =============================================================================


class TestBlockIntegration:
    """Tests for block creation alongside conversation/message rows."""

    def test_conversation_creates_block_row(self, service, conv_db):
        """start() inserts a block row with type='conversation' in the blocks table."""
        import cairn.play_db as play_db

        conv = service.start()
        conn = play_db._get_connection()

        cursor = conn.execute(
            "SELECT type, act_id FROM blocks WHERE id = ?", (conv.block_id,)
        )
        row = cursor.fetchone()

        assert row is not None
        assert row["type"] == "conversation"
        assert row["act_id"] == play_db.ARCHIVED_CONVERSATIONS_ACT_ID

    def test_message_creates_block_row(self, service, conv_db):
        """add_message() inserts a block row with type='message' as child of the conversation block."""
        import cairn.play_db as play_db

        conv = service.start()
        msg = service.add_message(conv.id, "user", "Test")
        conn = play_db._get_connection()

        cursor = conn.execute(
            "SELECT type, parent_id FROM blocks WHERE id = ?", (msg.block_id,)
        )
        row = cursor.fetchone()

        assert row is not None
        assert row["type"] == "message"
        assert row["parent_id"] == conv.block_id

    def test_conversation_block_id_is_distinct_from_conversation_id(self, service):
        """The conversation block_id and the conversation id are different values."""
        conv = service.start()

        assert conv.block_id != conv.id

    def test_message_block_id_is_distinct_from_message_id(self, service):
        """The message block_id and the message id are different values."""
        conv = service.start()
        msg = service.add_message(conv.id, "user", "Hello")

        assert msg.block_id != msg.id

    def test_multiple_messages_each_get_unique_block(self, service, conv_db):
        """Each message receives its own unique block_id."""
        import cairn.play_db as play_db

        conv = service.start()
        msg1 = service.add_message(conv.id, "user", "First")
        msg2 = service.add_message(conv.id, "cairn", "Second")
        msg3 = service.add_message(conv.id, "user", "Third")

        block_ids = {msg1.block_id, msg2.block_id, msg3.block_id}
        assert len(block_ids) == 3

        # All three message blocks exist in the DB
        conn = play_db._get_connection()
        for block_id in block_ids:
            cursor = conn.execute("SELECT id FROM blocks WHERE id = ?", (block_id,))
            assert cursor.fetchone() is not None

    def test_conversation_block_uses_archived_conversations_act(self, service, conv_db):
        """The conversation block is parented to the archived-conversations system act."""
        import cairn.play_db as play_db

        conv = service.start()
        conn = play_db._get_connection()

        cursor = conn.execute(
            "SELECT act_id FROM blocks WHERE id = ?", (conv.block_id,)
        )
        row = cursor.fetchone()

        assert row is not None
        assert row["act_id"] == "archived-conversations"


# =============================================================================
# get_by_id
# =============================================================================


class TestGetById:
    """Tests for get_by_id lookup."""

    def test_get_by_id_returns_conversation(self, service):
        """get_by_id returns the correct conversation for a known ID."""
        conv = service.start()

        fetched = service.get_by_id(conv.id)

        assert fetched is not None
        assert fetched.id == conv.id
        assert fetched.status == "active"

    def test_get_by_id_returns_none_for_unknown_id(self, service):
        """get_by_id returns None for an ID that does not exist."""
        result = service.get_by_id("does-not-exist")

        assert result is None

    def test_get_by_id_reflects_latest_status(self, service):
        """get_by_id reads current state from the database after a transition."""
        conv = service.start()
        service.close(conv.id)

        fetched = service.get_by_id(conv.id)

        assert fetched is not None
        assert fetched.status == "ready_to_close"
