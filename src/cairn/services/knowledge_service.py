"""Knowledge Service - Learned knowledge management via MemoryService.

Provides unified interface for managing learned knowledge entries.
Archives are handled by ArchiveService.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from ..play_db import _get_connection
from .memory_service import MemoryService

logger = logging.getLogger(__name__)


@dataclass
class LearnedEntryInfo:
    """Information about a learned knowledge entry."""

    entry_id: str
    category: str  # "fact", "lesson", "decision", "preference", "observation"
    content: str
    learned_at: str
    source_archive_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "category": self.category,
            "content": self.content,
            "learned_at": self.learned_at,
            "source_archive_id": self.source_archive_id,
        }


@dataclass
class KnowledgeStats:
    """Statistics about learned knowledge."""

    total_entries: int
    facts: int
    lessons: int
    decisions: int
    preferences: int
    observations: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_entries": self.total_entries,
            "facts": self.facts,
            "lessons": self.lessons,
            "decisions": self.decisions,
            "preferences": self.preferences,
            "observations": self.observations,
        }


class KnowledgeService:
    """Unified service for learned knowledge management backed by MemoryService."""

    def __init__(self) -> None:
        self._mem_service = MemoryService()

    def search(
        self,
        query: str,
        act_id: str | None = None,
        limit: int = 20,
    ) -> list[LearnedEntryInfo]:
        """Search learned knowledge by content.

        Args:
            query: Search query
            act_id: Filter by act (None for play level)
            limit: Maximum results

        Returns:
            List of matching LearnedEntryInfo
        """
        conn = _get_connection()
        query_lower = query.lower()

        if act_id is not None:
            cursor = conn.execute(
                """SELECT id, memory_type, narrative, created_at, source
                   FROM memories
                   WHERE status = 'approved'
                   AND destination_act_id = ?
                   AND LOWER(narrative) LIKE ?
                   ORDER BY created_at DESC
                   LIMIT ?""",
                (act_id, f"%{query_lower}%", limit),
            )
        else:
            cursor = conn.execute(
                """SELECT id, memory_type, narrative, created_at, source
                   FROM memories
                   WHERE status = 'approved'
                   AND (destination_act_id IS NULL OR is_your_story = 1)
                   AND LOWER(narrative) LIKE ?
                   ORDER BY created_at DESC
                   LIMIT ?""",
                (f"%{query_lower}%", limit),
            )

        results = []
        for row in cursor.fetchall():
            source = row["source"] or ""
            source_archive_id = source.split(":")[-1] if source.startswith("archive_service:") else None
            results.append(LearnedEntryInfo(
                entry_id=row["id"],
                category=row["memory_type"] or "observation",
                content=row["narrative"],
                learned_at=row["created_at"],
                source_archive_id=source_archive_id,
            ))
        return results

    def list_entries(
        self,
        act_id: str | None = None,
        category: str | None = None,
        limit: int = 100,
    ) -> list[LearnedEntryInfo]:
        """List learned knowledge entries.

        Args:
            act_id: Filter by act (None for play level)
            category: Filter by memory_type
            limit: Maximum results

        Returns:
            List of LearnedEntryInfo
        """
        conn = _get_connection()

        conditions = ["status = 'approved'"]
        params: list[Any] = []

        if act_id is not None:
            conditions.append("destination_act_id = ?")
            params.append(act_id)
        else:
            conditions.append("(destination_act_id IS NULL OR is_your_story = 1)")

        if category is not None:
            conditions.append("memory_type = ?")
            params.append(category)

        params.append(limit)
        where = " AND ".join(conditions)

        cursor = conn.execute(
            f"SELECT id, memory_type, narrative, created_at, source "
            f"FROM memories WHERE {where} ORDER BY created_at DESC LIMIT ?",
            params,
        )

        results = []
        for row in cursor.fetchall():
            source = row["source"] or ""
            source_archive_id = source.split(":")[-1] if source.startswith("archive_service:") else None
            results.append(LearnedEntryInfo(
                entry_id=row["id"],
                category=row["memory_type"] or "observation",
                content=row["narrative"],
                learned_at=row["created_at"],
                source_archive_id=source_archive_id,
            ))
        return results

    def add_entry(
        self,
        content: str,
        category: str = "observation",
        act_id: str | None = None,
        source_archive_id: str | None = None,
    ) -> LearnedEntryInfo | None:
        """Add a new learned knowledge entry.

        Args:
            content: The knowledge content
            category: Category (fact, lesson, decision, preference, observation)
            act_id: The act to associate with (None for play level)
            source_archive_id: Optional archive this came from

        Returns:
            The added entry, or None on failure
        """
        source = f"archive_service:{source_archive_id}" if source_archive_id else "knowledge_service"
        try:
            memory = self._mem_service.store(
                conversation_id="knowledge_service",
                narrative=content,
                destination_act_id=act_id,
                source=source,
                memory_type=category,
                status="approved",
            )
            return LearnedEntryInfo(
                entry_id=memory.id,
                category=category,
                content=content,
                learned_at=memory.created_at,
                source_archive_id=source_archive_id,
            )
        except Exception as e:
            logger.warning("Failed to add entry: %s", e)
            return None

    def add_entries_batch(
        self,
        entries: list[dict[str, str]],
        act_id: str | None = None,
        source_archive_id: str | None = None,
    ) -> list[LearnedEntryInfo]:
        """Add multiple learned knowledge entries.

        Args:
            entries: List of {"category": ..., "content": ...} dicts
            act_id: The act to associate with
            source_archive_id: Optional archive these came from

        Returns:
            List of actually added entries
        """
        source = f"archive_service:{source_archive_id}" if source_archive_id else "knowledge_service"
        added = []
        for entry in entries:
            content = entry.get("content", "")
            category = entry.get("category", "observation")
            if not content:
                continue
            try:
                memory = self._mem_service.store(
                    conversation_id="knowledge_service",
                    narrative=content,
                    destination_act_id=act_id,
                    source=source,
                    memory_type=category,
                    status="approved",
                )
                added.append(LearnedEntryInfo(
                    entry_id=memory.id,
                    category=category,
                    content=content,
                    learned_at=memory.created_at,
                    source_archive_id=source_archive_id,
                ))
            except Exception as e:
                logger.warning("Failed to add entry: %s", e)
        return added

    def delete_entry(
        self,
        entry_id: str,
        act_id: str | None = None,
    ) -> bool:
        """Delete a learned knowledge entry.

        Returns:
            True if deleted, False if not found
        """
        try:
            self._mem_service.delete(entry_id)
            return True
        except Exception:
            return False

    def get_stats(self, act_id: str | None = None) -> KnowledgeStats:
        """Get statistics about learned knowledge.

        Args:
            act_id: Filter by act (None for play level)

        Returns:
            KnowledgeStats with counts by category
        """
        conn = _get_connection()

        if act_id is not None:
            cursor = conn.execute(
                """SELECT memory_type, COUNT(*) as cnt
                   FROM memories
                   WHERE status = 'approved' AND destination_act_id = ?
                   GROUP BY memory_type""",
                (act_id,),
            )
        else:
            cursor = conn.execute(
                """SELECT memory_type, COUNT(*) as cnt
                   FROM memories
                   WHERE status = 'approved'
                   AND (destination_act_id IS NULL OR is_your_story = 1)
                   GROUP BY memory_type"""
            )

        counts: dict[str, int] = {}
        total = 0
        for row in cursor.fetchall():
            mtype = row["memory_type"] or "observation"
            counts[mtype] = row["cnt"]
            total += row["cnt"]

        return KnowledgeStats(
            total_entries=total,
            facts=counts.get("fact", 0),
            lessons=counts.get("lesson", 0),
            decisions=counts.get("decision", 0),
            preferences=counts.get("preference", 0),
            observations=counts.get("observation", 0),
        )

    def get_markdown(self, act_id: str | None = None) -> str:
        """Get learned knowledge as markdown for context injection.

        Args:
            act_id: Filter by act (None for play level)

        Returns:
            Markdown-formatted string
        """
        return self._mem_service.get_learned_markdown_from_db(act_id)

    def clear(self, act_id: str | None = None) -> None:
        """Clear all learned knowledge for an act.

        Args:
            act_id: The act to clear (None for play level)
        """
        from ..play_db import _transaction

        if act_id is not None:
            with _transaction() as txn:
                txn.execute(
                    "DELETE FROM memories WHERE destination_act_id = ?",
                    (act_id,),
                )
        else:
            with _transaction() as txn:
                txn.execute(
                    "DELETE FROM memories WHERE destination_act_id IS NULL OR is_your_story = 1"
                )

    def get_entry_count(self, act_id: str | None = None) -> int:
        """Get count of learned entries."""
        return self.get_stats(act_id).total_entries

    def get_categories(self) -> list[str]:
        """Get list of valid categories."""
        return ["fact", "lesson", "decision", "preference", "observation"]

    def export_to_dict(self, act_id: str | None = None) -> dict[str, Any]:
        """Export all learned knowledge as a dict.

        Returns:
            Dict with entries grouped by category
        """
        entries = self.list_entries(act_id=act_id, limit=10000)

        by_category: dict[str, list[dict[str, Any]]] = {
            "facts": [],
            "lessons": [],
            "decisions": [],
            "preferences": [],
            "observations": [],
        }

        category_map = {
            "fact": "facts",
            "lesson": "lessons",
            "decision": "decisions",
            "preference": "preferences",
            "observation": "observations",
        }

        for entry in entries:
            key = category_map.get(entry.category, "observations")
            by_category[key].append({
                "entry_id": entry.entry_id,
                "content": entry.content,
                "learned_at": entry.learned_at,
                "source_archive_id": entry.source_archive_id,
            })

        return {
            "act_id": act_id,
            "total_entries": len(entries),
            **by_category,
        }

    def import_from_dict(
        self,
        data: dict[str, Any],
        act_id: str | None = None,
        merge: bool = True,
    ) -> int:
        """Import learned knowledge from a dict.

        Args:
            data: Export dict with category lists
            act_id: The act to import into
            merge: If True, merge with existing; if False, replace

        Returns:
            Number of entries imported
        """
        if not merge:
            self.clear(act_id)

        entries_to_add = []

        category_map = {
            "facts": "fact",
            "lessons": "lesson",
            "decisions": "decision",
            "preferences": "preference",
            "observations": "observation",
        }

        for key, category in category_map.items():
            for item in data.get(key, []):
                content = item.get("content")
                if content:
                    entries_to_add.append({
                        "category": category,
                        "content": content,
                    })

        added = self.add_entries_batch(entries_to_add, act_id=act_id)
        return len(added)
