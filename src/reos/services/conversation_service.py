"""Conversation Lifecycle Service.

Manages the conversation lifecycle: active → ready_to_close → compressing → archived.

Key constraints:
- Singleton: Only one active conversation at a time (depth over breadth)
- State machine: Status transitions are enforced
- Block integration: Each conversation and message creates a block in the block hierarchy
- Messages are ordered by position within a conversation

See docs/CONVERSATION_LIFECYCLE_SPEC.md for full specification.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from ..play_db import (
    ARCHIVED_CONVERSATIONS_ACT_ID,
    _get_connection,
    _transaction,
    init_db,
)

logger = logging.getLogger(__name__)


# Valid state transitions
_VALID_TRANSITIONS: dict[str, set[str]] = {
    "active": {"ready_to_close"},
    "ready_to_close": {"compressing", "active"},  # active = resume
    "compressing": {"archived", "ready_to_close"},  # ready_to_close = retry on failure
    "archived": set(),  # terminal state
}


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _new_id() -> str:
    return uuid4().hex[:12]


@dataclass
class Conversation:
    """A conversation in the lifecycle."""

    id: str
    block_id: str
    status: str
    started_at: str
    last_message_at: str | None
    closed_at: str | None
    archived_at: str | None
    message_count: int
    is_paused: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "block_id": self.block_id,
            "status": self.status,
            "started_at": self.started_at,
            "last_message_at": self.last_message_at,
            "closed_at": self.closed_at,
            "archived_at": self.archived_at,
            "message_count": self.message_count,
            "is_paused": self.is_paused,
        }

    @classmethod
    def from_row(cls, row: Any) -> Conversation:
        return cls(
            id=row["id"],
            block_id=row["block_id"],
            status=row["status"],
            started_at=row["started_at"],
            last_message_at=row["last_message_at"],
            closed_at=row["closed_at"],
            archived_at=row["archived_at"],
            message_count=row["message_count"],
            is_paused=bool(row["is_paused"]),
        )


@dataclass
class Message:
    """A message within a conversation."""

    id: str
    conversation_id: str
    block_id: str
    role: str
    content: str
    position: int
    created_at: str
    active_act_id: str | None
    active_scene_id: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "conversation_id": self.conversation_id,
            "block_id": self.block_id,
            "role": self.role,
            "content": self.content,
            "position": self.position,
            "created_at": self.created_at,
            "active_act_id": self.active_act_id,
            "active_scene_id": self.active_scene_id,
        }

    @classmethod
    def from_row(cls, row: Any) -> Message:
        return cls(
            id=row["id"],
            conversation_id=row["conversation_id"],
            block_id=row["block_id"],
            role=row["role"],
            content=row["content"],
            position=row["position"],
            created_at=row["created_at"],
            active_act_id=row["active_act_id"],
            active_scene_id=row["active_scene_id"],
        )


class ConversationService:
    """Manages conversation lifecycle with singleton enforcement.

    All operations use the play_db connection (SQLite, WAL mode, thread-local).
    Block integration: conversations and messages create entries in both the
    domain table and the blocks table within a single transaction.
    """

    def __init__(self) -> None:
        init_db()

    def get_active(self) -> Conversation | None:
        """Get the currently active conversation, if any."""
        conn = _get_connection()
        cursor = conn.execute(
            "SELECT * FROM conversations WHERE status = 'active' LIMIT 1"
        )
        row = cursor.fetchone()
        return Conversation.from_row(row) if row else None

    def start(self) -> Conversation:
        """Start a new conversation.

        Enforces singleton constraint — raises if an active conversation exists.

        Returns:
            The new active Conversation.

        Raises:
            ConversationError: If an active conversation already exists.
        """
        existing = self.get_active()
        if existing:
            raise ConversationError(
                f"Cannot start a new conversation while one is active "
                f"(id={existing.id}, started={existing.started_at}). "
                f"Close the active conversation first."
            )

        conv_id = _new_id()
        block_id = f"block-{_new_id()}"
        now = _now_iso()

        with _transaction() as conn:
            # Create block for the conversation
            conn.execute(
                """INSERT INTO blocks (id, type, act_id, parent_id, page_id, scene_id,
                   position, created_at, updated_at)
                   VALUES (?, 'conversation', ?, NULL, NULL, NULL, 0, ?, ?)""",
                (block_id, ARCHIVED_CONVERSATIONS_ACT_ID, now, now),
            )

            # Create conversation row
            conn.execute(
                """INSERT INTO conversations (id, block_id, status, started_at,
                   message_count, is_paused)
                   VALUES (?, ?, 'active', ?, 0, 0)""",
                (conv_id, block_id, now),
            )

        logger.info("Started conversation %s", conv_id)
        return Conversation(
            id=conv_id,
            block_id=block_id,
            status="active",
            started_at=now,
            last_message_at=None,
            closed_at=None,
            archived_at=None,
            message_count=0,
            is_paused=False,
        )

    def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        *,
        active_act_id: str | None = None,
        active_scene_id: str | None = None,
    ) -> Message:
        """Add a message to an active conversation.

        Args:
            conversation_id: The conversation to add the message to.
            role: Message role ('user', 'cairn', 'reos', 'riva', 'system').
            content: Message content text.
            active_act_id: Optional Act context when this message was sent.
            active_scene_id: Optional Scene context when this message was sent.

        Returns:
            The created Message.

        Raises:
            ConversationError: If the conversation is not active.
        """
        conv = self.get_by_id(conversation_id)
        if not conv:
            raise ConversationError(f"Conversation not found: {conversation_id}")
        if conv.status != "active":
            raise ConversationError(
                f"Cannot add message to conversation in '{conv.status}' state"
            )

        msg_id = _new_id()
        block_id = f"block-{_new_id()}"
        now = _now_iso()

        with _transaction() as conn:
            # Get next position
            cursor = conn.execute(
                "SELECT COALESCE(MAX(position), -1) + 1 FROM messages "
                "WHERE conversation_id = ?",
                (conversation_id,),
            )
            position = cursor.fetchone()[0]

            # Create block for the message
            conn.execute(
                """INSERT INTO blocks (id, type, act_id, parent_id, page_id, scene_id,
                   position, created_at, updated_at)
                   VALUES (?, 'message', ?, ?, NULL, NULL, ?, ?, ?)""",
                (block_id, ARCHIVED_CONVERSATIONS_ACT_ID, conv.block_id, position, now, now),
            )

            # Create message row
            conn.execute(
                """INSERT INTO messages (id, conversation_id, block_id, role, content,
                   position, created_at, active_act_id, active_scene_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    msg_id, conversation_id, block_id, role, content,
                    position, now, active_act_id, active_scene_id,
                ),
            )

            # Update conversation metadata
            conn.execute(
                """UPDATE conversations
                   SET message_count = message_count + 1, last_message_at = ?
                   WHERE id = ?""",
                (now, conversation_id),
            )

        return Message(
            id=msg_id,
            conversation_id=conversation_id,
            block_id=block_id,
            role=role,
            content=content,
            position=position,
            created_at=now,
            active_act_id=active_act_id,
            active_scene_id=active_scene_id,
        )

    def get_messages(
        self,
        conversation_id: str,
        *,
        limit: int = 500,
    ) -> list[Message]:
        """Get messages for a conversation, ordered by position."""
        conn = _get_connection()
        cursor = conn.execute(
            "SELECT * FROM messages WHERE conversation_id = ? "
            "ORDER BY position ASC LIMIT ?",
            (conversation_id, limit),
        )
        return [Message.from_row(row) for row in cursor.fetchall()]

    def get_by_id(self, conversation_id: str) -> Conversation | None:
        """Get a conversation by ID."""
        conn = _get_connection()
        cursor = conn.execute(
            "SELECT * FROM conversations WHERE id = ?", (conversation_id,)
        )
        row = cursor.fetchone()
        return Conversation.from_row(row) if row else None

    def close(self, conversation_id: str) -> Conversation:
        """Initiate conversation closure (active → ready_to_close).

        This triggers the compression pipeline (handled by CompressionManager).

        Raises:
            ConversationError: If the conversation cannot be closed.
        """
        return self._transition(conversation_id, "ready_to_close")

    def resume(self, conversation_id: str) -> Conversation:
        """Resume a conversation that was ready to close (ready_to_close → active).

        Used when the user clicks "Resume" during the review step.
        """
        return self._transition(conversation_id, "active")

    def start_compression(self, conversation_id: str) -> Conversation:
        """Mark conversation as compressing (ready_to_close → compressing).

        Called by CompressionManager when it starts processing.
        """
        return self._transition(conversation_id, "compressing")

    def archive(self, conversation_id: str) -> Conversation:
        """Archive a compressed conversation (compressing → archived).

        Called after compression completes and memories are confirmed.
        """
        return self._transition(conversation_id, "archived")

    def fail_compression(self, conversation_id: str) -> Conversation:
        """Roll back a failed compression (compressing → ready_to_close).

        Called by CompressionManager when compression fails.
        """
        return self._transition(conversation_id, "ready_to_close")

    def pause(self, conversation_id: str) -> Conversation:
        """Pause an active conversation (suppresses idle observations)."""
        conv = self.get_by_id(conversation_id)
        if not conv:
            raise ConversationError(f"Conversation not found: {conversation_id}")
        if conv.status != "active":
            raise ConversationError("Can only pause an active conversation")

        now = _now_iso()
        with _transaction() as conn:
            conn.execute(
                "UPDATE conversations SET is_paused = 1, paused_at = ? WHERE id = ?",
                (now, conversation_id),
            )

        conv.is_paused = True
        return conv

    def unpause(self, conversation_id: str) -> Conversation:
        """Unpause a paused conversation."""
        conv = self.get_by_id(conversation_id)
        if not conv:
            raise ConversationError(f"Conversation not found: {conversation_id}")

        with _transaction() as conn:
            conn.execute(
                "UPDATE conversations SET is_paused = 0, paused_at = NULL WHERE id = ?",
                (conversation_id,),
            )

        conv.is_paused = False
        return conv

    def list_conversations(
        self,
        *,
        status: str | None = None,
        limit: int = 50,
    ) -> list[Conversation]:
        """List conversations, optionally filtered by status."""
        conn = _get_connection()
        if status:
            cursor = conn.execute(
                "SELECT * FROM conversations WHERE status = ? "
                "ORDER BY started_at DESC LIMIT ?",
                (status, limit),
            )
        else:
            cursor = conn.execute(
                "SELECT * FROM conversations ORDER BY started_at DESC LIMIT ?",
                (limit,),
            )
        return [Conversation.from_row(row) for row in cursor.fetchall()]

    def _transition(self, conversation_id: str, target_status: str) -> Conversation:
        """Transition a conversation to a new status with validation."""
        conv = self.get_by_id(conversation_id)
        if not conv:
            raise ConversationError(f"Conversation not found: {conversation_id}")

        valid = _VALID_TRANSITIONS.get(conv.status, set())
        if target_status not in valid:
            raise ConversationError(
                f"Invalid transition: {conv.status} → {target_status}. "
                f"Valid transitions from '{conv.status}': {valid or 'none (terminal state)'}"
            )

        now = _now_iso()
        with _transaction() as conn:
            # Set status-specific timestamps
            updates = ["status = ?"]
            params: list[Any] = [target_status]

            if target_status == "ready_to_close":
                updates.append("closed_at = ?")
                params.append(now)
            elif target_status == "archived":
                updates.append("archived_at = ?")
                params.append(now)

            params.append(conversation_id)
            conn.execute(
                f"UPDATE conversations SET {', '.join(updates)} WHERE id = ?",
                params,
            )

        logger.info(
            "Conversation %s: %s → %s", conversation_id, conv.status, target_status
        )
        conv.status = target_status
        return conv


class ConversationError(Exception):
    """Raised when a conversation operation fails."""
