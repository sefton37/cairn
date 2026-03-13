"""Priority Learning Service.

Extracts boost rules from reorder history so future surfacing automatically
reflects user preferences. The user's drag-and-drop behavior is training data.

Rules are feature-based (not ML): transparent, explainable, and effective
after just 3-5 reorders.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from ..play_db import get_active_boost_rules, get_reorder_history_stats, upsert_boost_rule

if TYPE_CHECKING:
    from ..cairn.models import SurfacedItem

logger = logging.getLogger(__name__)

# Feature descriptions for human-readable rule labels
_FEATURE_DESCRIPTIONS = {
    "act": "You tend to prioritize {value} items",
    "entity_type": "You tend to prioritize {value}s",
    "stage": "You tend to prioritize {value} items",
    "time_of_day": "You tend to prioritize differently in the {value}",
}


class PriorityLearningService:
    """Extracts boost rules from reorder history."""

    def extract_rules(self) -> list[dict[str, Any]]:
        """Analyze reorder_history and create/update priority_boost_rules.

        For each feature dimension, compute average position delta
        (how much items with that feature were moved UP on average).
        Convert to a normalized boost score.

        Returns:
            List of rule dicts that were created/updated.
        """
        stats = get_reorder_history_stats()
        now = datetime.now(timezone.utc).isoformat()
        rules: list[dict[str, Any]] = []

        for stat in stats:
            # Clamp improvement to [-1.0, +1.0]
            raw_improvement = stat["avg_improvement"]
            boost = max(-1.0, min(1.0, raw_improvement))

            # Confidence scales with sample count: full confidence at 10 samples
            confidence = min(1.0, stat["sample_count"] / 10.0)

            # Final boost = raw boost * confidence
            final_boost = boost * confidence

            # Build human-readable description
            template = _FEATURE_DESCRIPTIONS.get(
                stat["feature_type"], "Learned priority rule for {value}"
            )
            description = template.format(value=stat["description_value"])

            rule = {
                "id": str(uuid.uuid4()),
                "feature_type": stat["feature_type"],
                "feature_value": stat["feature_value"],
                "boost_score": round(final_boost, 4),
                "confidence": round(confidence, 4),
                "sample_count": stat["sample_count"],
                "description": description,
                "active": 1,
                "created_at": now,
                "updated_at": now,
            }

            try:
                upsert_boost_rule(rule)
                rules.append(rule)
            except Exception:
                logger.debug(
                    "Failed to upsert rule %s:%s",
                    stat["feature_type"],
                    stat["feature_value"],
                    exc_info=True,
                )

        return rules

    def get_active_boosts(self) -> dict[str, float]:
        """Return {feature_key: boost_score} for all active rules.

        feature_key format: "act:{act_id}", "entity_type:email",
        "stage:in_progress", "time_of_day:morning"
        """
        rules = get_active_boost_rules()
        return {
            f"{r['feature_type']}:{r['feature_value']}": r["boost_score"]
            for r in rules
        }

    def compute_item_boost(self, item: SurfacedItem, boosts: dict[str, float]) -> float:
        """Compute total boost for a surfaced item by summing matching rules.

        Args:
            item: The surfaced item to compute boost for.
            boosts: Active boost rules from get_active_boosts().

        Returns:
            Total boost score (can be negative).
        """
        total = 0.0

        # Act-based boost
        if item.act_id:
            total += boosts.get(f"act:{item.act_id}", 0.0)

        # Entity type boost
        total += boosts.get(f"entity_type:{item.entity_type}", 0.0)

        # Stage-based boost (scenes only)
        if hasattr(item, "metadata") and item.metadata:
            stage = getattr(item.metadata, "stage", None)
            if stage:
                total += boosts.get(f"stage:{stage}", 0.0)

        # Time-of-day boost (use current time)
        hour = datetime.now(timezone.utc).hour
        if 5 <= hour <= 11:
            bucket = "morning"
        elif 12 <= hour <= 17:
            bucket = "afternoon"
        elif 18 <= hour <= 23:
            bucket = "evening"
        else:
            bucket = "night"
        total += boosts.get(f"time_of_day:{bucket}", 0.0)

        return total

    def compute_boosts_for_items(
        self, items: list[SurfacedItem]
    ) -> dict[str, float]:
        """Compute boost scores for a list of surfaced items.

        Returns:
            {entity_id: boost_score} mapping.
        """
        boosts = self.get_active_boosts()
        if not boosts:
            return {}
        return {item.entity_id: self.compute_item_boost(item, boosts) for item in items}

    def get_boost_reasons(
        self, item: SurfacedItem, boosts: dict[str, float]
    ) -> list[str]:
        """Return human-readable reasons for an item's boost.

        Args:
            item: The surfaced item.
            boosts: Active boost rules from get_active_boosts().

        Returns:
            List of description strings for matching rules.
        """
        rules = get_active_boost_rules()
        reasons = []

        for rule in rules:
            key = f"{rule['feature_type']}:{rule['feature_value']}"
            if key not in boosts:
                continue

            matches = False
            if rule["feature_type"] == "act" and item.act_id == rule["feature_value"]:
                matches = True
            elif rule["feature_type"] == "entity_type" and item.entity_type == rule["feature_value"]:
                matches = True
            elif rule["feature_type"] == "stage":
                if hasattr(item, "metadata") and item.metadata:
                    stage = getattr(item.metadata, "stage", None)
                    if stage == rule["feature_value"]:
                        matches = True
            elif rule["feature_type"] == "time_of_day":
                # Time-of-day always matches current bucket
                hour = datetime.now(timezone.utc).hour
                if 5 <= hour <= 11:
                    bucket = "morning"
                elif 12 <= hour <= 17:
                    bucket = "afternoon"
                elif 18 <= hour <= 23:
                    bucket = "evening"
                else:
                    bucket = "night"
                if bucket == rule["feature_value"]:
                    matches = True

            if matches and rule.get("description"):
                reasons.append(rule["description"])

        return reasons

    def get_rules_for_display(self) -> list[dict[str, Any]]:
        """Return rules formatted for UI display."""
        return get_active_boost_rules()
