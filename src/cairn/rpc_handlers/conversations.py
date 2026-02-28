"""Conversation lifecycle RPC handlers.

Manages the conversation lifecycle: start, close, resume, messages, status.
These handlers wrap ConversationService and present results in RPC format.
"""

from __future__ import annotations

from typing import Any

from cairn.db import Database
from cairn.services.compression_manager import get_compression_manager
from cairn.services.conversation_service import ConversationError, ConversationService

from ._base import require_params, rpc_handler

# Singleton service instance (stateless, just wraps DB operations)
_service: ConversationService | None = None


def _get_service() -> ConversationService:
    global _service
    if _service is None:
        _service = ConversationService()
    return _service


@rpc_handler("lifecycle/conversations/get_active")
def handle_conversations_get_active(db: Database) -> dict[str, Any]:
    """Get the currently active conversation, if any."""
    service = _get_service()
    conv = service.get_active()
    return {"conversation": conv.to_dict() if conv else None}


@require_params()
@rpc_handler("lifecycle/conversations/start")
def handle_conversations_start(db: Database) -> dict[str, Any]:
    """Start a new conversation (singleton enforced)."""
    service = _get_service()
    try:
        conv = service.start()
        return {"conversation": conv.to_dict()}
    except ConversationError as e:
        # Return the error in a structured way instead of raising
        # The existing active conversation is useful context
        active = service.get_active()
        return {
            "error": str(e),
            "active_conversation": active.to_dict() if active else None,
        }


@require_params("conversation_id")
@rpc_handler("lifecycle/conversations/close")
def handle_conversations_close(db: Database, *, conversation_id: str) -> dict[str, Any]:
    """Close an active conversation (triggers compression).

    Transitions to ready_to_close and submits a compression job to the
    background CompressionManager.
    """
    service = _get_service()
    conv = service.close(conversation_id)

    # Submit compression job to background manager
    manager = get_compression_manager()
    status = manager.submit(conversation_id)

    return {
        "conversation": conv.to_dict(),
        "compression": status.to_dict(),
    }


@require_params("conversation_id")
@rpc_handler("lifecycle/conversations/resume")
def handle_conversations_resume(db: Database, *, conversation_id: str) -> dict[str, Any]:
    """Resume a conversation that was ready to close."""
    service = _get_service()
    conv = service.resume(conversation_id)
    return {"conversation": conv.to_dict()}


@require_params("conversation_id", "role", "content")
@rpc_handler("lifecycle/conversations/add_message")
def handle_conversations_add_message(
    db: Database,
    *,
    conversation_id: str,
    role: str,
    content: str,
    active_act_id: str | None = None,
    active_scene_id: str | None = None,
) -> dict[str, Any]:
    """Add a message to the active conversation."""
    service = _get_service()
    msg = service.add_message(
        conversation_id,
        role,
        content,
        active_act_id=active_act_id,
        active_scene_id=active_scene_id,
    )
    return {"message": msg.to_dict()}


@require_params("conversation_id")
@rpc_handler("lifecycle/conversations/messages")
def handle_conversations_messages(
    db: Database,
    *,
    conversation_id: str,
    limit: int = 500,
) -> dict[str, Any]:
    """Get messages for a conversation."""
    service = _get_service()
    messages = service.get_messages(conversation_id, limit=limit)
    return {"messages": [m.to_dict() for m in messages]}


@rpc_handler("lifecycle/conversations/list")
def handle_conversations_list(
    db: Database,
    *,
    status: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """List conversations, optionally filtered by status."""
    service = _get_service()
    conversations = service.list_conversations(status=status, limit=limit)
    return {"conversations": [c.to_dict() for c in conversations]}


@require_params("conversation_id")
@rpc_handler("lifecycle/conversations/pause")
def handle_conversations_pause(db: Database, *, conversation_id: str) -> dict[str, Any]:
    """Pause an active conversation."""
    service = _get_service()
    conv = service.pause(conversation_id)
    return {"conversation": conv.to_dict()}


@require_params("conversation_id")
@rpc_handler("lifecycle/conversations/unpause")
def handle_conversations_unpause(db: Database, *, conversation_id: str) -> dict[str, Any]:
    """Unpause a paused conversation."""
    service = _get_service()
    conv = service.unpause(conversation_id)
    return {"conversation": conv.to_dict()}


@require_params("conversation_id")
@rpc_handler("lifecycle/conversations/compression_status")
def handle_conversations_compression_status(
    db: Database, *, conversation_id: str
) -> dict[str, Any]:
    """Get the compression status for a conversation."""
    manager = get_compression_manager()
    status = manager.get_status(conversation_id)
    return {"status": status.to_dict() if status else None}


@require_params("query")
@rpc_handler("lifecycle/conversations/search")
def handle_conversations_search(
    db: Database,
    *,
    query: str,
    status: str | None = "archived",
    limit: int = 20,
    offset: int = 0,
    since: str | None = None,
    until: str | None = None,
) -> dict[str, Any]:
    """Search conversation messages by keyword using FTS5."""
    service = _get_service()
    results = service.search_messages(
        query,
        status=status or "archived",
        limit=limit,
        offset=offset,
        since=since,
        until=until,
    )
    return {"results": results, "count": len(results)}


@rpc_handler("lifecycle/conversations/list_enhanced")
def handle_conversations_list_enhanced(
    db: Database,
    *,
    status: str | None = "archived",
    limit: int = 50,
    offset: int = 0,
    since: str | None = None,
    until: str | None = None,
    has_memories: bool | None = None,
) -> dict[str, Any]:
    """List conversations with summaries and memory counts."""
    service = _get_service()
    conversations = service.list_with_summaries(
        status=status or "archived",
        limit=limit,
        offset=offset,
        since=since,
        until=until,
        has_memories=has_memories,
    )
    return {"conversations": conversations, "count": len(conversations)}


@require_params("conversation_id")
@rpc_handler("lifecycle/conversations/detail")
def handle_conversations_detail(
    db: Database,
    *,
    conversation_id: str,
) -> dict[str, Any]:
    """Get full conversation detail with messages, memories, and summary."""
    service = _get_service()
    detail = service.get_conversation_detail(conversation_id)
    return detail
