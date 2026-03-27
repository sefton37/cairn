"""Context Service - Context management and source toggling.

Provides unified interface for context budget management.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from ..context_meter import (
    MODEL_CONTEXT_LIMITS,
    RESERVED_TOKENS,
    ContextSource,
    ContextStats,
    calculate_context_stats,
    estimate_tokens,
)
from ..context_sources import DISABLEABLE_SOURCES, VALID_SOURCE_NAMES
from ..db import Database

logger = logging.getLogger(__name__)


@dataclass
class ContextStatsResult:
    """Context usage statistics."""

    estimated_tokens: int
    context_limit: int
    reserved_tokens: int
    available_tokens: int
    usage_percent: float
    message_count: int
    warning_level: str
    sources: list[dict[str, Any]] | None = None

    def to_dict(self) -> dict[str, Any]:
        result = {
            "estimated_tokens": self.estimated_tokens,
            "context_limit": self.context_limit,
            "reserved_tokens": self.reserved_tokens,
            "available_tokens": self.available_tokens,
            "usage_percent": round(self.usage_percent, 1),
            "message_count": self.message_count,
            "warning_level": self.warning_level,
        }
        if self.sources:
            result["sources"] = self.sources
        return result

    @classmethod
    def from_context_stats(cls, stats: ContextStats) -> ContextStatsResult:
        return cls(
            estimated_tokens=stats.estimated_tokens,
            context_limit=stats.context_limit,
            reserved_tokens=stats.reserved_tokens,
            available_tokens=stats.available_tokens,
            usage_percent=stats.usage_percent,
            message_count=stats.message_count,
            warning_level=stats.warning_level,
            sources=[s.to_dict() for s in stats.sources] if stats.sources else None,
        )


class ContextService:
    """Unified service for context management.

    Uses database for disabled_sources to maintain consistency with RPC handlers.
    Both CLI and UI share the same source of truth.
    """

    def __init__(self, db: Database):
        self._db = db

    def _get_disabled_sources(self) -> set[str]:
        """Get disabled sources from database (single source of truth)."""
        disabled_str = self._db.get_state(key="context_disabled_sources")
        if disabled_str and isinstance(disabled_str, str):
            return set(s.strip() for s in disabled_str.split(",") if s.strip())
        return set()

    def _save_disabled_sources(self, disabled: set[str]) -> None:
        """Save disabled sources to database."""
        self._db.set_state(key="context_disabled_sources", value=",".join(sorted(disabled)))

    def get_stats(
        self,
        conversation_id: str | None = None,
        include_breakdown: bool = True,
    ) -> ContextStatsResult:
        """Get context usage statistics.

        Args:
            conversation_id: Optional conversation to analyze
            include_breakdown: Whether to include per-source breakdown

        Returns:
            ContextStatsResult with usage information
        """
        # Get messages for the conversation
        messages = []
        if conversation_id:
            messages = self._db.get_messages(conversation_id=conversation_id, limit=1000)

        # Get context components
        system_prompt, play_context, learned_kb, system_state, codebase_context = (
            self._get_context_components()
        )

        # Get disabled sources from database (single source of truth)
        disabled_sources = self._get_disabled_sources()

        # Calculate stats
        stats = calculate_context_stats(
            messages=messages,
            system_prompt=system_prompt,
            play_context=play_context,
            learned_kb=learned_kb,
            system_state=system_state,
            codebase_context=codebase_context,
            include_breakdown=include_breakdown,
            disabled_sources=disabled_sources,
        )

        return ContextStatsResult.from_context_stats(stats)

    def toggle_source(
        self,
        source_name: str,
        enabled: bool,
    ) -> ContextStatsResult:
        """Enable or disable a context source.

        Persists to database so changes are shared between CLI and UI.

        Args:
            source_name: Name of the source (system_prompt, play_context, etc.)
            enabled: Whether to enable the source

        Returns:
            Updated context stats
        """
        # Validate source name (using shared constant)
        if source_name not in VALID_SOURCE_NAMES:
            logger.warning("Invalid source name: %s", source_name)
            return self.get_stats()

        # Don't allow disabling non-disableable sources (system_prompt, messages)
        if not enabled and source_name not in DISABLEABLE_SOURCES:
            logger.warning("Cannot disable source: %s", source_name)
            return self.get_stats()

        # Get current disabled sources from database
        disabled_sources = self._get_disabled_sources()

        if enabled:
            disabled_sources.discard(source_name)
        else:
            disabled_sources.add(source_name)

        # Save to database (single source of truth)
        self._save_disabled_sources(disabled_sources)

        logger.info("Context source %s: %s", source_name, "enabled" if enabled else "disabled")
        return self.get_stats()

    def get_disabled_sources(self) -> list[str]:
        """Get list of currently disabled sources."""
        return list(self._get_disabled_sources())

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count for text."""
        return estimate_tokens(text)

    def get_model_limits(self) -> dict[str, int]:
        """Get context limits for different model sizes."""
        return dict(MODEL_CONTEXT_LIMITS)

    def set_context_limit(self, limit: int) -> None:
        """Override the context limit.

        Args:
            limit: New context limit in tokens
        """
        # Store in database state for persistence
        self._db.set_state(key="context_limit", value=str(limit))
        logger.info("Context limit set to %d tokens", limit)

    def get_context_limit(self) -> int:
        """Get the current context limit."""
        limit = self._db.get_state(key="context_limit")
        if limit and isinstance(limit, str):
            try:
                return int(limit)
            except ValueError:
                pass
        return MODEL_CONTEXT_LIMITS["medium"]

    def _get_context_components(self) -> tuple[str, str, str, str, str]:
        """Get all context components for stats calculation.

        Returns:
            Tuple of (system_prompt, play_context, learned_kb, system_state, codebase_context)
        """
        from ..play_fs import kb_read as play_kb_read
        from ..play_fs import list_acts as play_list_acts

        # System prompt (approximate)
        system_prompt = (
            "You are CAIRN. You embody No One: presence that waits to be invited..."
            # This is just an approximation for token counting
        )

        # Play context
        play_context = ""
        try:
            play_context = play_kb_read(act_id="your-story", path="kb.md")
        except Exception as e:
            logger.warning("Failed to read Play context: %s", e)

        # Learned knowledge
        learned_kb = ""
        try:
            from .memory_service import MemoryService
            _, active_act_id = play_list_acts()
            mem_service = MemoryService()
            learned_kb = mem_service.get_learned_markdown_from_db(active_act_id)
        except Exception as e:
            logger.warning("Failed to get learned knowledge: %s", e)

        # System state (system_state module was extracted with ReOS; no-op here)
        system_state = ""

        # Codebase context (self-awareness)
        codebase_context = ""
        try:
            from ..codebase_index import get_codebase_context

            codebase_context = get_codebase_context()
        except Exception as e:
            logger.debug("Failed to get codebase context: %s", e)

        return system_prompt, play_context, learned_kb, system_state, codebase_context

    # --- Archive Access ---

    def list_archives(self, act_id: str | None = None) -> list[dict[str, Any]]:
        """List conversation archives from archive_metadata table.

        Args:
            act_id: Filter by act (None for play level)

        Returns:
            List of archive metadata dicts
        """
        from ..play_db import _get_connection

        conn = _get_connection()
        if act_id is not None:
            cursor = conn.execute(
                """SELECT archive_id, act_id, conversation_id, linking_reason,
                          topics, sentiment, created_at
                   FROM archive_metadata
                   WHERE act_id = ?
                   ORDER BY created_at DESC""",
                (act_id,),
            )
        else:
            cursor = conn.execute(
                """SELECT archive_id, act_id, conversation_id, linking_reason,
                          topics, sentiment, created_at
                   FROM archive_metadata
                   ORDER BY created_at DESC"""
            )

        results = []
        for row in cursor.fetchall():
            msg_count = 0
            if row["conversation_id"]:
                cur2 = conn.execute(
                    "SELECT COUNT(*) as cnt FROM messages WHERE conversation_id = ?",
                    (row["conversation_id"],),
                )
                cnt_row = cur2.fetchone()
                if cnt_row:
                    msg_count = cnt_row["cnt"]

            results.append({
                "archive_id": row["archive_id"],
                "act_id": row["act_id"],
                "title": row["archive_id"],
                "created_at": row["created_at"],
                "archived_at": row["created_at"],
                "message_count": msg_count,
                "summary": row["linking_reason"] or "",
            })
        return results

    def get_archive(self, archive_id: str, act_id: str | None = None) -> dict[str, Any] | None:
        """Get a specific archive with messages from DB.

        Returns:
            Archive dict with messages, or None if not found
        """
        from ..play_db import _get_connection

        conn = _get_connection()
        cursor = conn.execute(
            "SELECT * FROM archive_metadata WHERE archive_id = ?",
            (archive_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None

        messages: list[dict[str, Any]] = []
        if row["conversation_id"]:
            cur2 = conn.execute(
                "SELECT role, content, created_at FROM messages WHERE conversation_id = ? ORDER BY created_at",
                (row["conversation_id"],),
            )
            messages = [
                {"role": r["role"], "content": r["content"], "created_at": r["created_at"]}
                for r in cur2.fetchall()
            ]

        return {
            "archive_id": archive_id,
            "act_id": row["act_id"],
            "title": archive_id,
            "created_at": row["created_at"],
            "archived_at": row["created_at"],
            "message_count": len(messages),
            "messages": messages,
            "summary": row["linking_reason"] or "",
        }

    def search_archives(
        self,
        query: str,
        act_id: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Search archives by content via messages FTS.

        Returns:
            List of matching archive metadata
        """
        from ..play_db import _get_connection

        conn = _get_connection()
        query_lower = f"%{query.lower()}%"

        # Find conversation_ids with matching messages
        cur = conn.execute(
            "SELECT DISTINCT conversation_id FROM messages WHERE LOWER(content) LIKE ? LIMIT ?",
            (query_lower, limit),
        )
        matching_conv_ids = {row["conversation_id"] for row in cur.fetchall()}

        if not matching_conv_ids:
            return []

        placeholders = ",".join("?" * len(matching_conv_ids))
        params: list[Any] = list(matching_conv_ids)

        if act_id is not None:
            cur2 = conn.execute(
                f"SELECT archive_id, act_id, conversation_id, linking_reason, created_at "
                f"FROM archive_metadata WHERE conversation_id IN ({placeholders}) AND act_id = ?",
                params + [act_id],
            )
        else:
            cur2 = conn.execute(
                f"SELECT archive_id, act_id, conversation_id, linking_reason, created_at "
                f"FROM archive_metadata WHERE conversation_id IN ({placeholders})",
                params,
            )

        results = []
        for row in cur2.fetchall():
            results.append({
                "archive_id": row["archive_id"],
                "act_id": row["act_id"],
                "title": row["archive_id"],
                "created_at": row["created_at"],
                "archived_at": row["created_at"],
                "message_count": 0,
                "summary": row["linking_reason"] or "",
            })
        return results

    def delete_archive(self, archive_id: str, act_id: str | None = None) -> bool:
        """Delete an archive from archive_metadata.

        Returns:
            True if deleted successfully
        """
        from ..play_db import _get_connection, _transaction

        conn = _get_connection()
        cur = conn.execute(
            "SELECT archive_id FROM archive_metadata WHERE archive_id = ?",
            (archive_id,),
        )
        if not cur.fetchone():
            return False

        with _transaction() as txn:
            txn.execute("DELETE FROM archive_metadata WHERE archive_id = ?", (archive_id,))
        return True
