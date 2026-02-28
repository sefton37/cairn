"""Priority Signal Service.

Persists user drag-reorder of attention cards into the attention_priorities
table. Analysis and memory creation are handled separately by
PriorityAnalysisService via CAIRN conversation.
"""

from __future__ import annotations

import logging
from typing import Any

from ..play_db import set_attention_priorities

logger = logging.getLogger(__name__)


class PrioritySignalService:
    """Persists attention card reorder into priority table."""

    def process_reorder(
        self,
        ordered_scene_ids: list[str],
    ) -> dict[str, Any]:
        """Persist reorder to attention_priorities table.

        Args:
            ordered_scene_ids: Scene IDs in user's desired order (index 0 = top).

        Returns:
            Dict with priorities_updated count.
        """
        set_attention_priorities(ordered_scene_ids)

        return {
            "priorities_updated": len(ordered_scene_ids),
        }
