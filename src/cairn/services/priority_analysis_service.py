"""Priority Analysis Service.

When the user reorders attention cards, this service builds a structured
synthetic message capturing the full context (old order, new order, moved item,
scene details) and routes it through CAIRN for analysis. CAIRN proposes
memories/lessons conversationally — the user approves via normal chat.
"""

from __future__ import annotations

import logging
from typing import Any

from ..db import Database

logger = logging.getLogger(__name__)


class PriorityAnalysisService:
    """Analyzes attention reorder via CAIRN conversation."""

    def analyze_reorder(
        self,
        db: Database,
        ordered_scene_ids: list[str],
        old_priorities: dict[str, int],
        scene_details: list[dict[str, Any]],
        conversation_id: str,
    ) -> str:
        """Build context from reorder and get CAIRN's analysis.

        Args:
            db: Database instance for ChatAgent.
            ordered_scene_ids: Scene IDs in new order (index 0 = top).
            old_priorities: {scene_id: rank} from before the reorder.
            scene_details: List of dicts with scene metadata (title, stage,
                          notes, start_date, end_date, act_id, act_title).
            conversation_id: Active conversation to inject analysis into.

        Returns:
            CAIRN's analysis text (proposed memories/lessons).

        Raises:
            Exception: Propagated from ChatAgent if LLM call fails.
        """
        synthetic_message = self._build_synthetic_message(
            ordered_scene_ids, old_priorities, scene_details
        )

        # Late import to avoid circular dependency: agent imports services at module level
        from ..agent import ChatAgent

        agent = ChatAgent(db=db)
        response = agent.respond(
            synthetic_message,
            conversation_id=conversation_id,
            agent_type="cairn",
            is_system_initiated=True,
        )
        return response.answer

    def _build_synthetic_message(
        self,
        ordered_scene_ids: list[str],
        old_priorities: dict[str, int],
        scene_details: list[dict[str, Any]],
    ) -> str:
        """Construct the synthetic message for CAIRN analysis."""
        detail_lookup = {d["scene_id"]: d for d in scene_details}

        # Build previous order section
        prev_lines = self._build_order_lines(old_priorities, detail_lookup, is_old=True)

        # Build new order section with moved-item annotation
        new_priorities = {sid: idx for idx, sid in enumerate(ordered_scene_ids)}
        moved_id, old_pos, new_pos = self._detect_moved_item(old_priorities, new_priorities)
        new_lines = self._build_order_lines(
            new_priorities, detail_lookup, is_old=False,
            moved_id=moved_id, old_pos=old_pos,
        )

        # Build change summary
        change_line = ""
        if moved_id:
            moved_title = detail_lookup.get(moved_id, {}).get("title", moved_id)
            change_line = (
                f'\nCHANGE: "{moved_title}" moved from position '
                f"{old_pos + 1} to position {new_pos + 1}."
            )

        # Build scene details section
        detail_lines = []
        for sid in ordered_scene_ids:
            d = detail_lookup.get(sid)
            if not d:
                continue
            title = d.get("title", sid)
            act_title = d.get("act_title", "unknown")
            stage = d.get("stage", "unknown")
            start = d.get("start_date") or "not set"
            end = d.get("end_date") or "not set"
            notes = (d.get("notes") or "none")[:300]
            detail_lines.append(
                f'"{title}" (Act: {act_title}, Stage: {stage})\n'
                f"  Timing: {start} - {end}\n"
                f"  Notes: {notes}"
            )

        parts = [
            "[SYSTEM EVENT — Priority Reorder]",
            "",
            'The user manually reordered the "What Needs Attention" pane.',
            "",
            "PREVIOUS ORDER:",
            "\n".join(prev_lines) if prev_lines else "(no previous ordering)",
            "",
            "NEW ORDER:",
            "\n".join(new_lines),
        ]

        if change_line:
            parts.append(change_line)

        parts.extend([
            "",
            "SCENE DETAILS:",
            "\n".join(detail_lines) if detail_lines else "(no details available)",
            "",
            "Based on this reorder, propose one or two concise memory statements about what",
            "the user considers important right now. Frame each as a lesson learned about",
            "their priorities. Then ask the user whether these observations should be saved",
            "as memories.",
        ])

        return "\n".join(parts)

    def _build_order_lines(
        self,
        priorities: dict[str, int],
        detail_lookup: dict[str, dict[str, Any]],
        *,
        is_old: bool,
        moved_id: str | None = None,
        old_pos: int | None = None,
    ) -> list[str]:
        """Build numbered order lines from a priorities dict."""
        if not priorities:
            return []

        sorted_items = sorted(priorities.items(), key=lambda x: x[1])
        lines = []
        for sid, rank in sorted_items:
            d = detail_lookup.get(sid, {})
            title = d.get("title", sid)
            urgency = d.get("urgency", "unknown")
            stage = d.get("stage", "unknown")
            start = d.get("start_date")
            timing = f"starts {start}" if start else "no date"

            line = f'{rank + 1}. "{title}" — {urgency}, {timing}, Stage: {stage}'

            # Annotate moved item in new order
            if not is_old and moved_id and sid == moved_id and old_pos is not None:
                line += f"  ← MOVED from position {old_pos + 1}"

            lines.append(line)
        return lines

    @staticmethod
    def _detect_moved_item(
        old_priorities: dict[str, int],
        new_priorities: dict[str, int],
    ) -> tuple[str | None, int | None, int | None]:
        """Find the item with the largest rank delta between old and new order.

        Returns:
            (moved_id, old_position, new_position) or (None, None, None).
        """
        if not old_priorities or not new_priorities:
            return None, None, None

        max_delta = 0
        moved_id = None
        old_pos = None
        new_pos = None

        for sid in new_priorities:
            if sid in old_priorities:
                delta = abs(old_priorities[sid] - new_priorities[sid])
                if delta > max_delta:
                    max_delta = delta
                    moved_id = sid
                    old_pos = old_priorities[sid]
                    new_pos = new_priorities[sid]

        # Also check items that are new (not in old_priorities) — treat as large move
        for sid in new_priorities:
            if sid not in old_priorities:
                # New item, consider it the "moved" one if no bigger delta found
                if moved_id is None:
                    moved_id = sid
                    old_pos = len(old_priorities)  # Was at "end" implicitly
                    new_pos = new_priorities[sid]

        return moved_id, old_pos, new_pos
