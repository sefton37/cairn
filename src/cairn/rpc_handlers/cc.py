"""RPC handlers for Claude Code agent management (Helm Phase 2).

Seven methods for agent CRUD and session lifecycle:
- cc/agents/list, cc/agents/create, cc/agents/delete
- cc/session/send, cc/session/poll, cc/session/stop, cc/session/history
"""

from __future__ import annotations

import os
from typing import Any

from cairn.db import Database
from trcore.cc_manager import CCManager

_manager: CCManager | None = None


def _get_manager() -> CCManager:
    global _manager
    if _manager is None:
        from cairn.services.cc_db_adapter import CairnCCDatabase

        _manager = CCManager(
            db=CairnCCDatabase(),
            on_session_complete=_on_session_complete,
            context_injector=_inject_context,
        )
    return _manager


def _on_session_complete(
    *,
    agent_id: str,
    agent_name: str,
    agent_purpose: str,
    transcript: str,
    stats: dict[str, Any],
) -> None:
    """Cairn-specific: submit completed session to the observer for memory extraction."""
    from datetime import datetime, timezone

    from cairn.services.cc_session_observer import CCSessionJob, get_cc_session_observer

    get_cc_session_observer().submit(
        CCSessionJob(
            agent_id=agent_id,
            agent_name=agent_name,
            agent_purpose=agent_purpose,
            transcript=transcript,
            stats=stats,
            completed_at=datetime.now(timezone.utc).isoformat(),
        )
    )


def _inject_context(text: str) -> str:
    """Cairn-specific: inject relevant approved memories into the prompt.

    Only 'approved' memories are injected — pending_review must never
    influence Claude Code behavior without user vetting.
    Returns original text unchanged if injection fails or yields nothing.
    """
    try:
        from cairn.memory.retriever import MemoryRetriever

        retriever = MemoryRetriever()
        ctx = retriever.retrieve_conversation_memories(
            text, status="approved", max_results=3
        )
        if not ctx.matches:
            return text

        block = ctx.to_prompt_block()
        if not block:
            return text

        return f"[Cairn context — relevant memories from prior sessions]\n{block}\n[End context]\n\n{text}"
    except Exception:
        import logging

        logging.getLogger(__name__).warning("Context injection failed, proceeding without")
        return text


def handle_cc_agents_list(db: Database) -> dict[str, Any]:
    """List all agents for the current user."""
    username = os.environ.get("USER", "unknown")
    mgr = _get_manager()
    agents = mgr.list_agents(username)
    return {"agents": agents}


def handle_cc_agents_create(
    db: Database, *, name: str, purpose: str = "", linked_scene_id: str | None = None
) -> dict[str, Any]:
    """Create a new Claude Code agent with workspace."""
    username = os.environ.get("USER", "unknown")
    mgr = _get_manager()
    agent = mgr.create_agent(username, name, purpose)

    # Persist linked_scene_id if provided
    if linked_scene_id:
        from cairn.play_db import _get_connection, _transaction

        conn = _get_connection()
        # Validate scene exists
        scene = conn.execute(
            "SELECT scene_id FROM scenes WHERE scene_id = ?", (linked_scene_id,)
        ).fetchone()
        if scene:
            with _transaction() as conn:
                conn.execute(
                    "UPDATE cc_agents SET linked_scene_id = ? WHERE id = ?",
                    (linked_scene_id, agent["id"]),
                )
            agent["linked_scene_id"] = linked_scene_id

    return {"agent": agent}


def handle_cc_agents_delete(db: Database, *, agent_id: str) -> dict[str, Any]:
    """Delete an agent. Kills running process if any."""
    mgr = _get_manager()
    return mgr.delete_agent(agent_id)


async def handle_cc_session_send(
    db: Database, *, agent_id: str, text: str
) -> dict[str, Any]:
    """Send a message to an agent. Spawns a Claude Code process."""
    mgr = _get_manager()
    return await mgr.send_message(agent_id, text)


def handle_cc_session_poll(
    db: Database, *, agent_id: str, since: int = 0
) -> dict[str, Any]:
    """Poll for events from a running agent."""
    mgr = _get_manager()
    return mgr.poll_events(agent_id, since)


async def handle_cc_session_stop(db: Database, *, agent_id: str) -> dict[str, Any]:
    """Stop a running Claude Code process."""
    mgr = _get_manager()
    return await mgr.stop_session(agent_id)


def handle_cc_session_history(
    db: Database, *, agent_id: str, limit: int = 100
) -> dict[str, Any]:
    """Get conversation history for an agent."""
    mgr = _get_manager()
    messages = mgr.get_history(agent_id, limit)
    return {"messages": messages}


def handle_cc_insights_list(
    db: Database, *, agent_id: str | None = None, status: str = "pending_review"
) -> dict[str, Any]:
    """List cc_insights, optionally filtered by agent and status."""
    from cairn.play_db import _get_connection

    conn = _get_connection()
    conditions = []
    params: list[str] = []

    if agent_id:
        conditions.append("i.agent_id = ?")
        params.append(agent_id)
    if status:
        conditions.append("i.status = ?")
        params.append(status)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    rows = conn.execute(
        f"""SELECT i.id, i.agent_id, i.session_completed_at, i.user_messages,
               i.files_touched, i.insight_type, i.insight_text, i.memory_id,
               i.status, i.created_at, a.name as agent_name
           FROM cc_insights i
           LEFT JOIN cc_agents a ON i.agent_id = a.id
           {where}
           ORDER BY i.created_at DESC LIMIT 100""",
        params,
    ).fetchall()

    return {
        "insights": [
            {
                "id": r["id"],
                "agent_id": r["agent_id"],
                "agent_name": r["agent_name"] or "",
                "session_completed_at": r["session_completed_at"],
                "user_messages": r["user_messages"],
                "files_touched": r["files_touched"],
                "insight_type": r["insight_type"],
                "insight_text": r["insight_text"],
                "memory_id": r["memory_id"],
                "status": r["status"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]
    }


def handle_cc_insights_accept(db: Database, *, insight_id: str) -> dict[str, Any]:
    """Accept an insight (status -> 'accepted')."""
    from cairn.play_db import _get_connection, _transaction
    from cairn.rpc_handlers import RpcError

    conn = _get_connection()
    row = conn.execute("SELECT id FROM cc_insights WHERE id = ?", (insight_id,)).fetchone()
    if not row:
        raise RpcError(code=-32003, message="Insight not found")

    with _transaction() as conn:
        conn.execute(
            "UPDATE cc_insights SET status = 'accepted' WHERE id = ?", (insight_id,)
        )
    return {"ok": True, "insight_id": insight_id}


def handle_cc_insights_dismiss(db: Database, *, insight_id: str) -> dict[str, Any]:
    """Dismiss an insight (status -> 'dismissed')."""
    from cairn.play_db import _get_connection, _transaction
    from cairn.rpc_handlers import RpcError

    conn = _get_connection()
    row = conn.execute("SELECT id FROM cc_insights WHERE id = ?", (insight_id,)).fetchone()
    if not row:
        raise RpcError(code=-32003, message="Insight not found")

    with _transaction() as conn:
        conn.execute(
            "UPDATE cc_insights SET status = 'dismissed' WHERE id = ?", (insight_id,)
        )
    return {"ok": True, "insight_id": insight_id}
