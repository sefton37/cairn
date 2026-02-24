"""Memory lifecycle RPC handlers.

Manages memory review, routing, search, and correction.
These handlers wrap MemoryService and present results in RPC format.
"""

from __future__ import annotations

from typing import Any

from reos.db import Database
from reos.services.memory_service import MemoryError, MemoryService

from ._base import require_params, rpc_handler

# Singleton service instance
_service: MemoryService | None = None


def _get_service() -> MemoryService:
    global _service
    if _service is None:
        _service = MemoryService()
    return _service


@rpc_handler("lifecycle/memories/pending")
def handle_memories_pending(
    db: Database, *, limit: int = 50
) -> dict[str, Any]:
    """Get memories pending user review."""
    service = _get_service()
    memories = service.get_pending_review(limit=limit)
    return {"memories": [m.to_dict() for m in memories]}


@require_params("memory_id")
@rpc_handler("lifecycle/memories/get")
def handle_memories_get(db: Database, *, memory_id: str) -> dict[str, Any]:
    """Get a memory by ID, including entities and deltas."""
    service = _get_service()
    memory = service.get_by_id(memory_id)
    if not memory:
        return {"memory": None}

    entities = service.get_entities(memory_id)
    deltas = service.get_state_deltas(memory_id)

    result = memory.to_dict()
    result["entities"] = entities
    result["state_deltas"] = deltas
    return {"memory": result}


@require_params("memory_id")
@rpc_handler("lifecycle/memories/approve")
def handle_memories_approve(db: Database, *, memory_id: str) -> dict[str, Any]:
    """Approve a memory (enters reasoning pool)."""
    service = _get_service()
    try:
        memory = service.approve(memory_id)
        return {"memory": memory.to_dict()}
    except MemoryError as e:
        return {"error": str(e)}


@require_params("memory_id")
@rpc_handler("lifecycle/memories/reject")
def handle_memories_reject(db: Database, *, memory_id: str) -> dict[str, Any]:
    """Reject a memory (excluded from reasoning)."""
    service = _get_service()
    try:
        memory = service.reject(memory_id)
        return {"memory": memory.to_dict()}
    except MemoryError as e:
        return {"error": str(e)}


@require_params("memory_id", "narrative")
@rpc_handler("lifecycle/memories/edit")
def handle_memories_edit(
    db: Database, *, memory_id: str, narrative: str
) -> dict[str, Any]:
    """Edit a memory's narrative before approval."""
    service = _get_service()
    try:
        memory = service.edit_narrative(memory_id, narrative)
        return {"memory": memory.to_dict()}
    except MemoryError as e:
        return {"error": str(e)}


@require_params("memory_id", "destination_act_id")
@rpc_handler("lifecycle/memories/route")
def handle_memories_route(
    db: Database, *, memory_id: str, destination_act_id: str
) -> dict[str, Any]:
    """Route a memory to a specific Act."""
    service = _get_service()
    try:
        memory = service.route(memory_id, destination_act_id)
        return {"memory": memory.to_dict()}
    except MemoryError as e:
        return {"error": str(e)}


@require_params("query")
@rpc_handler("lifecycle/memories/search")
def handle_memories_search(
    db: Database,
    *,
    query: str,
    status: str | None = "approved",
    top_k: int = 10,
) -> dict[str, Any]:
    """Search memories by semantic similarity."""
    service = _get_service()
    results = service.search(query, status=status, top_k=top_k)
    return {
        "results": [
            {"memory": m.to_dict(), "similarity": round(score, 4)}
            for m, score in results
        ]
    }


@require_params("conversation_id")
@rpc_handler("lifecycle/memories/by_conversation")
def handle_memories_by_conversation(
    db: Database, *, conversation_id: str
) -> dict[str, Any]:
    """Get all memories for a conversation."""
    service = _get_service()
    memories = service.get_by_conversation(conversation_id)
    return {"memories": [m.to_dict() for m in memories]}


@rpc_handler("lifecycle/memories/list")
def handle_memories_list(
    db: Database,
    *,
    status: str | None = None,
    act_id: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """List memories with optional filters."""
    service = _get_service()
    memories = service.list_memories(status=status, act_id=act_id, limit=limit)
    return {"memories": [m.to_dict() for m in memories]}


@require_params("memory_id", "corrected_narrative", "conversation_id")
@rpc_handler("lifecycle/memories/correct")
def handle_memories_correct(
    db: Database,
    *,
    memory_id: str,
    corrected_narrative: str,
    conversation_id: str,
) -> dict[str, Any]:
    """Correct a memory (creates new memory, supersedes old).

    The new memory inherits the old memory's signal_count.
    """
    service = _get_service()
    try:
        new_memory = service.correct(memory_id, corrected_narrative, conversation_id)
        return {"memory": new_memory.to_dict()}
    except MemoryError as e:
        return {"error": str(e)}
