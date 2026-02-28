"""State Briefing Service.

On new conversation start, generates a compressed situational awareness
document injected into the first turn's context. Provides warm starts
that make each conversation feel continuous.

The briefing is cached in the state_briefings table. Stale after 24 hours.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from ..play_db import _get_connection, _transaction, init_db
from ..providers.ollama import OllamaProvider

logger = logging.getLogger(__name__)

# Briefing is stale after 24 hours
_STALE_HOURS = 24

# Prompt templates — target < 300 token output, 1B-viable
_BRIEFING_SYSTEM = """\
You are a situational awareness synthesizer. Given memory snippets, \
open tasks, and recent context, write a BRIEF orientation document for \
resuming work. Keep it under 250 words. Focus on: what is in progress, \
what is waiting, and what was recently decided."""

_BRIEFING_USER = """\
Top memories:
{memories_block}

Active work items:
{active_scenes_block}

User's attention priorities:
{priorities_block}

Open threads:
{open_threads_block}

Last session summary:
{last_summary}

Write the orientation document now."""


# =============================================================================
# Data types
# =============================================================================


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _new_id() -> str:
    return uuid4().hex[:12]


@dataclass
class StateBriefing:
    """A cached situational awareness document."""

    id: str
    content: str          # Markdown, target < 300 tokens
    token_count: int | None
    trigger: str          # 'app_start' | 'new_conversation' | 'manual'
    generated_at: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "content": self.content,
            "token_count": self.token_count,
            "trigger": self.trigger,
            "generated_at": self.generated_at,
        }


# =============================================================================
# Service
# =============================================================================


class StateBriefingService:
    """Generates and caches situational awareness briefings.

    Briefings are short orientation documents injected at conversation start.
    A cached briefing is returned if it was generated within the last 24 hours;
    otherwise a new one is generated from the current knowledge base state.

    Usage:
        service = StateBriefingService()
        briefing = service.get_or_generate()
        # inject briefing.content into first-turn context
    """

    def __init__(self, provider: OllamaProvider | None = None) -> None:
        self._provider = provider
        init_db()

    def _get_provider(self) -> OllamaProvider:
        if self._provider is None:
            self._provider = OllamaProvider()
        return self._provider

    # -------------------------------------------------------------------------
    # Staleness check
    # -------------------------------------------------------------------------

    def _is_stale(self, briefing: StateBriefing) -> bool:
        """Return True if the briefing is older than _STALE_HOURS."""
        try:
            generated = datetime.fromisoformat(briefing.generated_at)
            # Ensure timezone-aware for comparison
            if generated.tzinfo is None:
                generated = generated.replace(tzinfo=UTC)
            cutoff = datetime.now(UTC) - timedelta(hours=_STALE_HOURS)
            return generated < cutoff
        except (ValueError, TypeError):
            return True

    # -------------------------------------------------------------------------
    # DB access
    # -------------------------------------------------------------------------

    def get_current(self) -> StateBriefing | None:
        """Get the most recent non-stale briefing from the DB.

        Returns None if no briefing exists or the most recent one is stale.
        """
        conn = _get_connection()
        cursor = conn.execute(
            "SELECT * FROM state_briefings ORDER BY generated_at DESC LIMIT 1"
        )
        row = cursor.fetchone()
        if row is None:
            return None

        briefing = StateBriefing(
            id=row["id"],
            content=row["content"],
            token_count=row["token_count"],
            trigger=row["trigger"],
            generated_at=row["generated_at"],
        )

        if self._is_stale(briefing):
            logger.debug("State briefing %s is stale, ignoring", briefing.id)
            return None

        return briefing

    def _save(self, briefing: StateBriefing) -> None:
        """Persist a briefing to the state_briefings table."""
        with _transaction() as conn:
            conn.execute(
                """INSERT INTO state_briefings (id, generated_at, content, token_count, trigger)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    briefing.id,
                    briefing.generated_at,
                    briefing.content,
                    briefing.token_count,
                    briefing.trigger,
                ),
            )

    # -------------------------------------------------------------------------
    # Knowledge base queries
    # -------------------------------------------------------------------------

    def _get_top_memories(self, limit: int = 5) -> list[str]:
        """Fetch top approved memories by signal_count (descending)."""
        conn = _get_connection()
        cursor = conn.execute(
            """SELECT narrative FROM memories
               WHERE status = 'approved'
               ORDER BY signal_count DESC
               LIMIT ?""",
            (limit,),
        )
        return [row["narrative"] for row in cursor.fetchall()]

    def _get_active_scenes(self) -> list[str]:
        """Fetch active Acts and in-progress/planning Scenes."""
        conn = _get_connection()
        cursor = conn.execute(
            """SELECT a.title AS act_title, s.title AS scene_title, s.stage
               FROM scenes s
               JOIN acts a ON s.act_id = a.act_id
               WHERE a.active = 1
                 AND s.stage IN ('in_progress', 'planning')
               ORDER BY s.stage DESC, s.updated_at DESC
               LIMIT 20""",
        )
        items = []
        for row in cursor.fetchall():
            stage_label = "In Progress" if row["stage"] == "in_progress" else "Planning"
            items.append(f"[{stage_label}] {row['act_title']} → {row['scene_title']}")
        return items

    def _get_open_threads(self, limit: int = 5) -> list[str]:
        """Fetch unapplied state deltas (open threads)."""
        conn = _get_connection()
        cursor = conn.execute(
            """SELECT d.delta_type, d.delta_data, m.narrative
               FROM memory_state_deltas d
               JOIN memories m ON d.memory_id = m.id
               WHERE d.applied = 0
               ORDER BY m.created_at DESC
               LIMIT ?""",
            (limit,),
        )
        import json

        threads = []
        for row in cursor.fetchall():
            delta_type = row["delta_type"]
            try:
                data = json.loads(row["delta_data"])
                detail = data.get("summary") or data.get("description") or str(data)[:120]
            except (ValueError, KeyError):
                detail = str(row["delta_data"])[:120]
            threads.append(f"[{delta_type}] {detail}")
        return threads

    def _get_last_summary(self) -> str:
        """Fetch the most recent conversation summary."""
        conn = _get_connection()
        cursor = conn.execute(
            "SELECT summary FROM conversation_summaries ORDER BY created_at DESC LIMIT 1"
        )
        row = cursor.fetchone()
        return row["summary"] if row else "(no prior summary)"

    def _get_attention_priorities(self, limit: int = 5) -> list[str]:
        """Fetch top user-prioritized attention items with scene titles."""
        conn = _get_connection()
        try:
            cursor = conn.execute(
                """SELECT s.title FROM attention_priorities ap
                   JOIN scenes s ON ap.scene_id = s.scene_id
                   ORDER BY ap.user_priority ASC
                   LIMIT ?""",
                (limit,),
            )
            return [
                f"#{i + 1}: {row['title']}"
                for i, row in enumerate(cursor.fetchall())
            ]
        except Exception:
            return []

    # -------------------------------------------------------------------------
    # Generation
    # -------------------------------------------------------------------------

    def generate(self, trigger: str = "new_conversation") -> StateBriefing:
        """Generate a fresh briefing via LLM and persist it.

        Queries the current knowledge base state (memories, scenes, open threads,
        last summary) and synthesizes a brief orientation document.

        Args:
            trigger: Source of the generation request.
                     One of 'app_start', 'new_conversation', 'manual'.

        Returns:
            The newly generated and persisted StateBriefing.
        """
        memories = self._get_top_memories()
        active_scenes = self._get_active_scenes()
        priorities = self._get_attention_priorities()
        open_threads = self._get_open_threads()
        last_summary = self._get_last_summary()

        memories_block = (
            "\n".join(f"- {m}" for m in memories) if memories else "(none)"
        )
        active_scenes_block = (
            "\n".join(f"- {s}" for s in active_scenes) if active_scenes else "(none)"
        )
        priorities_block = (
            "\n".join(f"- {p}" for p in priorities) if priorities else "(none)"
        )
        open_threads_block = (
            "\n".join(f"- {t}" for t in open_threads) if open_threads else "(none)"
        )

        user_prompt = _BRIEFING_USER.format(
            memories_block=memories_block,
            active_scenes_block=active_scenes_block,
            priorities_block=priorities_block,
            open_threads_block=open_threads_block,
            last_summary=last_summary,
        )

        try:
            provider = self._get_provider()
            content = provider.chat_text(
                system=_BRIEFING_SYSTEM,
                user=user_prompt,
                temperature=0.3,
            )
            content = (content or "").strip()
        except Exception as e:
            logger.warning("LLM generation failed for state briefing: %s", e)
            # Produce a minimal briefing from raw data so the service never fails silently
            lines = ["**Situational Awareness** (LLM unavailable)"]
            if memories:
                lines.append("\n**Recent memories:**")
                lines.extend(f"- {m}" for m in memories[:3])
            if active_scenes:
                lines.append("\n**Active work:**")
                lines.extend(f"- {s}" for s in active_scenes[:3])
            content = "\n".join(lines)

        # Rough token count: ~4 chars per token
        token_count = max(1, len(content) // 4)

        briefing = StateBriefing(
            id=_new_id(),
            content=content,
            token_count=token_count,
            trigger=trigger,
            generated_at=_now_iso(),
        )

        self._save(briefing)
        logger.info(
            "Generated state briefing %s (trigger=%s, ~%d tokens)",
            briefing.id,
            trigger,
            token_count,
        )
        return briefing

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def get_or_generate(self, trigger: str = "new_conversation") -> StateBriefing:
        """Return a fresh briefing: cached if within 24 hours, else regenerate.

        This is the primary entry point called at conversation start.

        Args:
            trigger: Used only if generation is needed.

        Returns:
            A non-stale StateBriefing.
        """
        current = self.get_current()
        if current is not None:
            logger.debug("Returning cached state briefing %s", current.id)
            return current

        return self.generate(trigger=trigger)
