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


# =============================================================================
# Knowledge Browser handlers
# =============================================================================


@require_params("query")
@rpc_handler("lifecycle/memories/search_fts")
def handle_memories_search_fts(
    db: Database,
    *,
    query: str,
    status: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict[str, Any]:
    """Search memories by keyword (FTS5)."""
    service = _get_service()
    results = service.search_fts(query, status=status, limit=limit, offset=offset)
    return {"results": results, "query": query, "total": len(results)}


@rpc_handler("lifecycle/memories/list_enhanced")
def handle_memories_list_enhanced(
    db: Database,
    *,
    status: str | None = None,
    act_id: str | None = None,
    entity_type: str | None = None,
    source: str | None = None,
    min_signal: int | None = None,
    limit: int = 50,
    offset: int = 0,
    order_by: str = "created_at",
) -> dict[str, Any]:
    """List memories with enhanced metadata."""
    service = _get_service()
    memories = service.list_enhanced(
        status=status,
        act_id=act_id,
        entity_type=entity_type,
        source=source,
        min_signal=min_signal,
        limit=limit,
        offset=offset,
        order_by=order_by,
    )
    return {"memories": memories}


@require_params("memory_id")
@rpc_handler("lifecycle/memories/supersession_chain")
def handle_memories_supersession_chain(
    db: Database,
    *,
    memory_id: str,
) -> dict[str, Any]:
    """Get the full supersession chain for a memory."""
    service = _get_service()
    chain = service.get_supersession_chain(memory_id)
    return {"chain": chain, "memory_id": memory_id, "length": len(chain)}


@require_params("memory_id")
@rpc_handler("lifecycle/memories/influence_log")
def handle_memories_influence_log(
    db: Database,
    *,
    memory_id: str,
    limit: int = 20,
) -> dict[str, Any]:
    """Get classification decisions this memory influenced."""
    service = _get_service()
    entries = service.get_influence_log(memory_id, limit=limit)
    return {"memory_id": memory_id, "entries": entries}


@rpc_handler("lifecycle/memories/entity_type_counts")
def handle_memories_entity_type_counts(
    db: Database,
    *,
    status: str = "approved",
) -> dict[str, Any]:
    """Get entity type counts for filter UI."""
    service = _get_service()
    counts = service.get_entity_type_counts(status=status)
    return {"counts": counts, "status": status}


@rpc_handler("lifecycle/memories/by_act")
def handle_memories_by_act(
    db: Database,
    *,
    status: str = "approved",
) -> dict[str, Any]:
    """Get memories grouped by destination Act."""
    service = _get_service()
    groups = service.get_act_memory_groups(status=status)
    return {"groups": groups, "status": status}


@rpc_handler("lifecycle/memories/open_threads")
def handle_memories_open_threads(
    db: Database,
    *,
    limit: int = 50,
) -> dict[str, Any]:
    """Get unresolved state deltas (open threads)."""
    service = _get_service()
    threads = service.get_open_threads(limit=limit)
    return {"threads": threads}


@require_params("memory_id", "delta_id")
@rpc_handler("lifecycle/memories/resolve_thread")
def handle_memories_resolve_thread(
    db: Database,
    *,
    memory_id: str,
    delta_id: str,
    resolution_note: str = "",
) -> dict[str, Any]:
    """Resolve an open thread (state delta)."""
    service = _get_service()
    try:
        result = service.resolve_thread(memory_id, delta_id, resolution_note=resolution_note)
        return {"delta": result}
    except MemoryError as e:
        return {"error": str(e)}
