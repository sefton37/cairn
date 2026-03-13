"""Priority Signal Service.

Persists user drag-reorder of attention cards into the attention_priorities
table. Records reorder history for priority learning. Analysis and memory
creation are handled separately by PriorityAnalysisService via CAIRN conversation.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from ..play_db import (
    get_attention_priorities,
    record_reorder_history,
    set_attention_priorities,
)

logger = logging.getLogger(__name__)


class PrioritySignalService:
    """Persists attention card reorder and records history for learning."""

    def process_reorder(
        self,
        ordered_scene_ids: list[str] | None = None,
        ordered_entities: list[tuple[str, str]] | None = None,
    ) -> dict[str, Any]:
        """Persist reorder and record history for learning.

        Args:
            ordered_scene_ids: Scene IDs in user's desired order (backward compat).
            ordered_entities: (entity_type, entity_id) pairs in desired order.

        Returns:
            Dict with priorities_updated count.
        """
        # Normalize to entity pairs
        entities = ordered_entities or [
            ("scene", sid) for sid in (ordered_scene_ids or [])
        ]

        # 1. Capture old priorities BEFORE persisting
        try:
            old_priorities = get_attention_priorities()
        except Exception:
            old_priorities = {}

        # 2. Persist new order (scene-only for existing table)
        scene_ids = [eid for etype, eid in entities if etype == "scene"]
        if scene_ids:
            set_attention_priorities(scene_ids)

        # 3. Record history with features
        self._record_reorder_history(entities, old_priorities)

        return {
            "priorities_updated": len(entities),
        }

    def _record_reorder_history(
        self,
        entities: list[tuple[str, str]],
        old_priorities: dict[str, int],
    ) -> None:
        """Record each item's position change with extracted features."""
        now = datetime.now(timezone.utc)
        timestamp = now.isoformat()
        total_items = len(entities)

        # Build old position map (scene_id -> old rank)
        old_position_map: dict[str, int] = {}
        for scene_id, rank in old_priorities.items():
            old_position_map[scene_id] = rank

        # Look up scene features in bulk
        scene_features = self._extract_scene_features(
            [eid for etype, eid in entities if etype == "scene"]
        )

        entries: list[dict] = []
        for new_pos, (entity_type, entity_id) in enumerate(entities):
            old_pos = old_position_map.get(entity_id)
            features = scene_features.get(entity_id, {})

            entries.append({
                "id": str(uuid.uuid4()),
                "reorder_timestamp": timestamp,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "old_position": old_pos,
                "new_position": new_pos,
                "total_items": total_items,
                "act_id": features.get("act_id"),
                "act_title": features.get("act_title"),
                "scene_stage": features.get("stage"),
                "urgency_at_reorder": features.get("urgency"),
                "has_calendar_event": 1 if features.get("has_calendar_event") else 0,
                "is_email": 1 if entity_type == "email" else 0,
                "hour_of_day": now.hour,
                "day_of_week": now.weekday(),
                "created_at": timestamp,
            })

        try:
            record_reorder_history(entries)
        except Exception:
            logger.debug("Failed to record reorder history", exc_info=True)

    def _extract_scene_features(self, scene_ids: list[str]) -> dict[str, dict]:
        """Look up features for scenes from the database."""
        if not scene_ids:
            return {}

        try:
            from ..play_db import _get_connection

            conn = _get_connection()
            placeholders = ",".join("?" * len(scene_ids))
            cursor = conn.execute(
                f"""SELECT s.scene_id, s.stage, s.act_id,
                           a.title as act_title,
                           s.calendar_event_start
                    FROM scenes s
                    LEFT JOIN acts a ON s.act_id = a.act_id
                    WHERE s.scene_id IN ({placeholders})""",
                scene_ids,
            )
            result = {}
            for row in cursor.fetchall():
                result[row["scene_id"]] = {
                    "act_id": row["act_id"],
                    "act_title": row["act_title"],
                    "stage": row["stage"],
                    "has_calendar_event": bool(row["calendar_event_start"]),
                }
            return result
        except Exception:
            logger.debug("Failed to extract scene features", exc_info=True)
            return {}
