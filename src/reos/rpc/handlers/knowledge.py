"""Knowledge handlers.

Manages archives, compaction, and learned knowledge.
"""

from __future__ import annotations

from typing import Any

from reos.db import Database
from reos.rpc.router import register
from reos.rpc.types import RpcError


# --------------------------------------------------------------------------
# Archive handlers
# --------------------------------------------------------------------------


@register("archive/save", needs_db=True)
def handle_archive_save(
    db: Database,
    *,
    conversation_id: str,
    act_id: str | None = None,
    title: str | None = None,
    generate_summary: bool = False,
) -> dict[str, Any]:
    """Archive a conversation."""
    from reos.knowledge_store import KnowledgeStore
    from reos.compact_extractor import generate_archive_summary

    raw_messages = db.get_messages(conversation_id=conversation_id, limit=500)
    if not raw_messages:
        raise RpcError(code=-32602, message="No messages in conversation")

    messages = [
        {
            "role": m["role"],
            "content": m["content"],
            "created_at": m.get("created_at", ""),
        }
        for m in raw_messages
    ]

    summary = ""
    if generate_summary:
        summary = generate_archive_summary(messages)

    store = KnowledgeStore()
    archive = store.save_archive(
        messages=messages,
        act_id=act_id,
        title=title,
        summary=summary,
    )

    return {
        "archive_id": archive.archive_id,
        "title": archive.title,
        "message_count": archive.message_count,
        "archived_at": archive.archived_at,
        "summary": archive.summary,
    }


@register("archive/list", needs_db=True)
def handle_archive_list(
    _db: Database,
    *,
    act_id: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """List archives for an act (or play level)."""
    from reos.knowledge_store import KnowledgeStore

    store = KnowledgeStore()
    archives = store.list_archives(act_id)[:limit]

    return {
        "archives": [
            {
                "archive_id": a.archive_id,
                "act_id": a.act_id,
                "title": a.title,
                "created_at": a.created_at,
                "archived_at": a.archived_at,
                "message_count": a.message_count,
                "summary": a.summary,
            }
            for a in archives
        ]
    }


@register("archive/get", needs_db=True)
def handle_archive_get(
    _db: Database,
    *,
    archive_id: str,
    act_id: str | None = None,
) -> dict[str, Any]:
    """Get a specific archive with full messages."""
    from reos.knowledge_store import KnowledgeStore

    store = KnowledgeStore()
    archive = store.get_archive(archive_id, act_id)

    if not archive:
        raise RpcError(code=-32602, message="Archive not found")

    return archive.to_dict()


@register("archive/delete", needs_db=True)
def handle_archive_delete(
    _db: Database,
    *,
    archive_id: str,
    act_id: str | None = None,
) -> dict[str, Any]:
    """Delete an archive."""
    from reos.knowledge_store import KnowledgeStore

    store = KnowledgeStore()
    deleted = store.delete_archive(archive_id, act_id)

    return {"ok": deleted}


@register("archive/search", needs_db=True)
def handle_archive_search(
    _db: Database,
    *,
    query: str,
    act_id: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Search archives by content."""
    from reos.knowledge_store import KnowledgeStore

    store = KnowledgeStore()
    archives = store.search_archives(query, act_id, limit)

    return {
        "archives": [
            {
                "archive_id": a.archive_id,
                "act_id": a.act_id,
                "title": a.title,
                "created_at": a.created_at,
                "archived_at": a.archived_at,
                "message_count": a.message_count,
                "summary": a.summary,
            }
            for a in archives
        ]
    }


# --------------------------------------------------------------------------
# Compact handlers
# --------------------------------------------------------------------------


@register("compact/preview", needs_db=True)
def handle_compact_preview(
    db: Database,
    *,
    conversation_id: str,
    act_id: str | None = None,
) -> dict[str, Any]:
    """Preview knowledge extraction before compacting."""
    from reos.knowledge_store import KnowledgeStore
    from reos.compact_extractor import extract_knowledge_from_messages

    raw_messages = db.get_messages(conversation_id=conversation_id, limit=500)
    if not raw_messages:
        raise RpcError(code=-32602, message="No messages in conversation")

    messages = [
        {"role": m["role"], "content": m["content"]}
        for m in raw_messages
    ]

    # Get existing knowledge to help LLM avoid duplicates
    store = KnowledgeStore()
    existing_kb = store.get_learned_markdown(act_id)

    # Extract knowledge
    entries = extract_knowledge_from_messages(
        messages,
        existing_knowledge=existing_kb,
    )

    return {
        "entries": entries,
        "message_count": len(messages),
        "existing_entry_count": store.get_learned_entry_count(act_id),
    }


@register("compact/apply", needs_db=True)
def handle_compact_apply(
    db: Database,
    *,
    conversation_id: str,
    act_id: str | None = None,
    entries: list[dict[str, str]],
    archive_first: bool = True,
) -> dict[str, Any]:
    """Apply compaction: save knowledge, optionally archive, then can clear chat."""
    from reos.knowledge_store import KnowledgeStore

    store = KnowledgeStore()

    # Optionally archive first
    archive_id = None
    if archive_first:
        raw_messages = db.get_messages(conversation_id=conversation_id, limit=500)
        if raw_messages:
            messages = [
                {
                    "role": m["role"],
                    "content": m["content"],
                    "created_at": m.get("created_at", ""),
                }
                for m in raw_messages
            ]
            archive = store.save_archive(
                messages=messages,
                act_id=act_id,
                title=None,
                summary="(compacted)",
            )
            archive_id = archive.archive_id

    # Add learned entries
    added = store.add_learned_entries(
        entries=entries,
        act_id=act_id,
        source_archive_id=archive_id,
        deduplicate=True,
    )

    return {
        "added_count": len(added),
        "archive_id": archive_id,
        "total_entries": store.get_learned_entry_count(act_id),
    }


# --------------------------------------------------------------------------
# Learned knowledge handlers
# --------------------------------------------------------------------------


@register("learned/get", needs_db=True)
def handle_learned_get(
    _db: Database,
    *,
    act_id: str | None = None,
) -> dict[str, Any]:
    """Get learned knowledge for an act."""
    from reos.knowledge_store import KnowledgeStore

    store = KnowledgeStore()
    kb = store.load_learned(act_id)

    return {
        "act_id": kb.act_id,
        "entry_count": len(kb.entries),
        "last_updated": kb.last_updated,
        "markdown": kb.to_markdown(),
        "entries": [e.to_dict() for e in kb.entries],
    }


@register("learned/clear", needs_db=True)
def handle_learned_clear(
    _db: Database,
    *,
    act_id: str | None = None,
) -> dict[str, Any]:
    """Clear all learned knowledge for an act."""
    from reos.knowledge_store import KnowledgeStore

    store = KnowledgeStore()
    store.clear_learned(act_id)
    return {"ok": True}
