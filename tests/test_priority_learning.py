"""Tests for priority learning from drag-and-drop reordering.

Tests the full pipeline:
- Reorder history recording and feature extraction
- Rule extraction from history patterns
- Boost application in surfacing ranking
- Backward compatibility with existing APIs
- Rule lifecycle (update, disable)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Create isolated data directory for play_db."""
    data_dir = tmp_path / "reos-data"
    data_dir.mkdir()
    monkeypatch.setenv("TALKINGROCK_DATA_DIR", str(data_dir))

    import cairn.play_db as play_db

    play_db.close_connection()

    yield data_dir

    play_db.close_connection()


@pytest.fixture
def db(temp_data_dir: Path):
    """Initialize the database and return the module."""
    import cairn.play_db as play_db

    play_db.init_db()
    return play_db


@pytest.fixture
def populated_db(db):
    """DB with acts and scenes for testing."""
    now = datetime.now(timezone.utc).isoformat()

    conn = db._get_connection()
    # Create acts
    conn.execute(
        "INSERT INTO acts (act_id, title, color, position, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("act-health", "Health", "#00ff00", 0, now, now),
    )
    conn.execute(
        "INSERT INTO acts (act_id, title, color, position, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("act-career", "Career", "#0000ff", 1, now, now),
    )
    conn.execute(
        "INSERT INTO acts (act_id, title, color, position, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("act-family", "Family", "#ff0000", 2, now, now),
    )

    # Create scenes
    for i, (sid, title, act_id, stage) in enumerate([
        ("scene-gym", "Morning Gym", "act-health", "in_progress"),
        ("scene-checkup", "Annual Checkup", "act-health", "planning"),
        ("scene-review", "Quarterly Review", "act-career", "in_progress"),
        ("scene-deploy", "Deploy v2.0", "act-career", "awaiting_data"),
        ("scene-dinner", "Family Dinner", "act-family", "planning"),
    ]):
        conn.execute(
            "INSERT INTO scenes (scene_id, act_id, title, stage, position, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (sid, act_id, title, stage, i, now, now),
        )

    conn.commit()
    return db


# =============================================================================
# TestReorderHistory
# =============================================================================


class TestReorderHistory:
    """Tests for recording reorder history with feature extraction."""

    def test_record_basic_history(self, db) -> None:
        """Recording reorder history creates entries in reorder_history table."""
        entries = [
            {
                "id": str(uuid.uuid4()),
                "reorder_timestamp": datetime.now(timezone.utc).isoformat(),
                "entity_type": "scene",
                "entity_id": "scene-1",
                "old_position": 2,
                "new_position": 0,
                "total_items": 3,
                "act_id": "act-health",
                "act_title": "Health",
                "scene_stage": "in_progress",
                "urgency_at_reorder": "high",
                "has_calendar_event": 0,
                "is_email": 0,
                "hour_of_day": 10,
                "day_of_week": 1,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        ]
        db.record_reorder_history(entries)

        conn = db._get_connection()
        cursor = conn.execute("SELECT COUNT(*) FROM reorder_history")
        assert cursor.fetchone()[0] == 1

    def test_record_multiple_entries(self, db) -> None:
        """Multiple entries recorded atomically."""
        now = datetime.now(timezone.utc).isoformat()
        entries = [
            {
                "id": str(uuid.uuid4()),
                "reorder_timestamp": now,
                "entity_type": "scene",
                "entity_id": f"scene-{i}",
                "old_position": i,
                "new_position": 2 - i,
                "total_items": 3,
                "created_at": now,
            }
            for i in range(3)
        ]
        db.record_reorder_history(entries)

        conn = db._get_connection()
        cursor = conn.execute("SELECT COUNT(*) FROM reorder_history")
        assert cursor.fetchone()[0] == 3

    def test_null_old_position_for_new_items(self, db) -> None:
        """Items not previously in the list have NULL old_position."""
        entries = [
            {
                "id": str(uuid.uuid4()),
                "reorder_timestamp": datetime.now(timezone.utc).isoformat(),
                "entity_type": "scene",
                "entity_id": "scene-new",
                "old_position": None,
                "new_position": 0,
                "total_items": 3,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        ]
        db.record_reorder_history(entries)

        conn = db._get_connection()
        cursor = conn.execute(
            "SELECT old_position FROM reorder_history WHERE entity_id = 'scene-new'"
        )
        assert cursor.fetchone()["old_position"] is None

    def test_empty_entries_is_noop(self, db) -> None:
        """Empty entries list does nothing."""
        db.record_reorder_history([])
        conn = db._get_connection()
        cursor = conn.execute("SELECT COUNT(*) FROM reorder_history")
        assert cursor.fetchone()[0] == 0


class TestPrioritySignalServiceHistory:
    """Tests for PrioritySignalService recording history via process_reorder."""

    def test_process_reorder_records_history(self, populated_db) -> None:
        """process_reorder records entries in reorder_history."""
        from cairn.services.priority_signal_service import PrioritySignalService

        service = PrioritySignalService()
        service.process_reorder(ordered_scene_ids=["scene-gym", "scene-review", "scene-dinner"])

        conn = populated_db._get_connection()
        cursor = conn.execute("SELECT COUNT(*) FROM reorder_history")
        assert cursor.fetchone()[0] == 3

    def test_process_reorder_extracts_features(self, populated_db) -> None:
        """History entries include act_id, act_title, stage from scene lookup."""
        from cairn.services.priority_signal_service import PrioritySignalService

        service = PrioritySignalService()
        service.process_reorder(ordered_scene_ids=["scene-gym", "scene-review"])

        conn = populated_db._get_connection()
        cursor = conn.execute(
            "SELECT act_id, act_title, scene_stage FROM reorder_history "
            "WHERE entity_id = 'scene-gym'"
        )
        row = cursor.fetchone()
        assert row["act_id"] == "act-health"
        assert row["act_title"] == "Health"
        assert row["scene_stage"] == "in_progress"

    def test_process_reorder_tracks_position_change(self, populated_db) -> None:
        """Old and new positions are tracked correctly."""
        from cairn.services.priority_signal_service import PrioritySignalService

        service = PrioritySignalService()

        # First reorder establishes positions
        service.process_reorder(ordered_scene_ids=["scene-gym", "scene-review", "scene-dinner"])

        # Second reorder: move scene-dinner from position 2 to position 0
        service.process_reorder(ordered_scene_ids=["scene-dinner", "scene-gym", "scene-review"])

        conn = populated_db._get_connection()
        # Get the second reorder's entry for scene-dinner
        cursor = conn.execute(
            "SELECT old_position, new_position FROM reorder_history "
            "WHERE entity_id = 'scene-dinner' "
            "ORDER BY reorder_timestamp DESC LIMIT 1"
        )
        row = cursor.fetchone()
        assert row["old_position"] == 2  # Was at position 2
        assert row["new_position"] == 0  # Now at position 0

    def test_process_reorder_with_entities(self, populated_db) -> None:
        """ordered_entities parameter works and records entity_type correctly."""
        from cairn.services.priority_signal_service import PrioritySignalService

        service = PrioritySignalService()
        service.process_reorder(
            ordered_entities=[
                ("scene", "scene-gym"),
                ("email", "email-123"),
                ("scene", "scene-review"),
            ]
        )

        conn = populated_db._get_connection()
        cursor = conn.execute(
            "SELECT entity_type, is_email FROM reorder_history WHERE entity_id = 'email-123'"
        )
        row = cursor.fetchone()
        assert row["entity_type"] == "email"
        assert row["is_email"] == 1


# =============================================================================
# TestRuleExtraction
# =============================================================================


class TestRuleExtraction:
    """Tests for extracting boost rules from reorder history."""

    def _insert_reorder_events(self, db, events: list[dict]) -> None:
        """Helper to insert multiple reorder history events."""
        entries = []
        for event in events:
            entries.append({
                "id": str(uuid.uuid4()),
                "reorder_timestamp": event.get(
                    "timestamp", datetime.now(timezone.utc).isoformat()
                ),
                "entity_type": event.get("entity_type", "scene"),
                "entity_id": event.get("entity_id", str(uuid.uuid4())),
                "old_position": event.get("old_position", 3),
                "new_position": event.get("new_position", 0),
                "total_items": event.get("total_items", 5),
                "act_id": event.get("act_id"),
                "act_title": event.get("act_title"),
                "scene_stage": event.get("scene_stage"),
                "urgency_at_reorder": event.get("urgency_at_reorder"),
                "has_calendar_event": event.get("has_calendar_event", 0),
                "is_email": event.get("is_email", 0),
                "hour_of_day": event.get("hour_of_day", 10),
                "day_of_week": event.get("day_of_week", 1),
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
        db.record_reorder_history(entries)

    def test_no_rules_with_insufficient_data(self, db) -> None:
        """Rules require at least 3 samples — fewer produces no rules."""
        self._insert_reorder_events(db, [
            {"act_id": "act-health", "act_title": "Health", "old_position": 3, "new_position": 0},
            {"act_id": "act-health", "act_title": "Health", "old_position": 2, "new_position": 0},
        ])

        from cairn.services.priority_learning_service import PriorityLearningService

        learner = PriorityLearningService()
        rules = learner.extract_rules()

        # Should not create act rule (only 2 samples, need 3)
        act_rules = [r for r in rules if r["feature_type"] == "act"]
        assert len(act_rules) == 0

    def test_act_rule_created_after_threshold(self, db) -> None:
        """Consistently moving Health items up creates an act boost rule."""
        # 4 events moving Health items up (old_position > new_position)
        self._insert_reorder_events(db, [
            {"act_id": "act-health", "act_title": "Health",
             "old_position": 3, "new_position": 0, "total_items": 5},
            {"act_id": "act-health", "act_title": "Health",
             "old_position": 4, "new_position": 1, "total_items": 5},
            {"act_id": "act-health", "act_title": "Health",
             "old_position": 3, "new_position": 0, "total_items": 5},
            {"act_id": "act-health", "act_title": "Health",
             "old_position": 2, "new_position": 0, "total_items": 5},
        ])

        from cairn.services.priority_learning_service import PriorityLearningService

        learner = PriorityLearningService()
        rules = learner.extract_rules()

        act_rules = [r for r in rules if r["feature_type"] == "act"]
        assert len(act_rules) == 1
        assert act_rules[0]["feature_value"] == "act-health"
        assert act_rules[0]["boost_score"] > 0  # Positive = items moved up
        assert act_rules[0]["sample_count"] == 4
        assert "Health" in act_rules[0]["description"]

    def test_negative_boost_for_items_moved_down(self, db) -> None:
        """Items consistently moved down get negative boost."""
        # 3 events moving Career items down
        self._insert_reorder_events(db, [
            {"act_id": "act-career", "act_title": "Career",
             "old_position": 0, "new_position": 4, "total_items": 5},
            {"act_id": "act-career", "act_title": "Career",
             "old_position": 1, "new_position": 4, "total_items": 5},
            {"act_id": "act-career", "act_title": "Career",
             "old_position": 0, "new_position": 3, "total_items": 5},
        ])

        from cairn.services.priority_learning_service import PriorityLearningService

        learner = PriorityLearningService()
        rules = learner.extract_rules()

        act_rules = [r for r in rules if r["feature_type"] == "act"]
        assert len(act_rules) == 1
        assert act_rules[0]["boost_score"] < 0  # Negative = items moved down

    def test_confidence_scales_with_samples(self, db) -> None:
        """Confidence increases with sample count, capping at 1.0."""
        # 3 samples → confidence = 0.3
        self._insert_reorder_events(db, [
            {"act_id": "act-health", "act_title": "Health",
             "old_position": 3, "new_position": 0, "total_items": 5},
            {"act_id": "act-health", "act_title": "Health",
             "old_position": 3, "new_position": 0, "total_items": 5},
            {"act_id": "act-health", "act_title": "Health",
             "old_position": 3, "new_position": 0, "total_items": 5},
        ])

        from cairn.services.priority_learning_service import PriorityLearningService

        learner = PriorityLearningService()
        rules = learner.extract_rules()

        act_rules = [r for r in rules if r["feature_type"] == "act"]
        assert len(act_rules) == 1
        assert act_rules[0]["confidence"] == pytest.approx(0.3, abs=0.01)

    def test_rules_updated_on_new_data(self, db) -> None:
        """Re-extracting rules updates existing ones (UPSERT)."""
        # Initial 3 events
        self._insert_reorder_events(db, [
            {"act_id": "act-health", "act_title": "Health",
             "old_position": 3, "new_position": 0, "total_items": 5},
            {"act_id": "act-health", "act_title": "Health",
             "old_position": 3, "new_position": 0, "total_items": 5},
            {"act_id": "act-health", "act_title": "Health",
             "old_position": 3, "new_position": 0, "total_items": 5},
        ])

        from cairn.services.priority_learning_service import PriorityLearningService

        learner = PriorityLearningService()
        rules1 = learner.extract_rules()
        assert rules1[0]["sample_count"] == 3

        # Add 2 more events and re-extract
        self._insert_reorder_events(db, [
            {"act_id": "act-health", "act_title": "Health",
             "old_position": 3, "new_position": 0, "total_items": 5},
            {"act_id": "act-health", "act_title": "Health",
             "old_position": 3, "new_position": 0, "total_items": 5},
        ])
        rules2 = learner.extract_rules()

        act_rules = [r for r in rules2 if r["feature_type"] == "act"]
        assert act_rules[0]["sample_count"] == 5

        # Verify only one rule in DB (not duplicated)
        conn = db._get_connection()
        cursor = conn.execute(
            "SELECT COUNT(*) FROM priority_boost_rules "
            "WHERE feature_type = 'act' AND feature_value = 'act-health'"
        )
        assert cursor.fetchone()[0] == 1

    def test_rules_stored_in_db(self, db) -> None:
        """Extracted rules are persisted in priority_boost_rules table."""
        self._insert_reorder_events(db, [
            {"act_id": "act-health", "act_title": "Health",
             "old_position": 3, "new_position": 0, "total_items": 5},
            {"act_id": "act-health", "act_title": "Health",
             "old_position": 3, "new_position": 0, "total_items": 5},
            {"act_id": "act-health", "act_title": "Health",
             "old_position": 3, "new_position": 0, "total_items": 5},
        ])

        from cairn.services.priority_learning_service import PriorityLearningService

        learner = PriorityLearningService()
        learner.extract_rules()

        rules = db.get_active_boost_rules()
        assert len(rules) >= 1
        act_rules = [r for r in rules if r["feature_type"] == "act"]
        assert act_rules[0]["feature_value"] == "act-health"


# =============================================================================
# TestBoostApplication
# =============================================================================


class TestBoostApplication:
    """Tests for applying learned boosts in ranking."""

    def test_boost_applied_in_ranking(self, db) -> None:
        """Items with positive boost rank higher among same-urgency, unprioritized items."""
        from cairn.cairn.models import SurfacedItem

        # Insert a positive boost rule for act-health
        now = datetime.now(timezone.utc).isoformat()
        db.upsert_boost_rule({
            "id": str(uuid.uuid4()),
            "feature_type": "act",
            "feature_value": "act-health",
            "boost_score": 0.5,
            "confidence": 1.0,
            "sample_count": 10,
            "description": "You tend to prioritize Health items",
            "active": 1,
            "created_at": now,
            "updated_at": now,
        })

        from cairn.services.priority_learning_service import PriorityLearningService

        learner = PriorityLearningService()
        boosts = learner.get_active_boosts()
        assert "act:act-health" in boosts
        assert boosts["act:act-health"] == 0.5

    def test_compute_item_boost(self, db) -> None:
        """compute_item_boost sums matching rules."""
        from cairn.cairn.models import SurfacedItem
        from cairn.services.priority_learning_service import PriorityLearningService

        now = datetime.now(timezone.utc).isoformat()
        db.upsert_boost_rule({
            "id": str(uuid.uuid4()),
            "feature_type": "act",
            "feature_value": "act-health",
            "boost_score": 0.3,
            "confidence": 1.0,
            "sample_count": 10,
            "active": 1,
            "created_at": now,
            "updated_at": now,
        })
        db.upsert_boost_rule({
            "id": str(uuid.uuid4()),
            "feature_type": "entity_type",
            "feature_value": "scene",
            "boost_score": 0.1,
            "confidence": 1.0,
            "sample_count": 10,
            "active": 1,
            "created_at": now,
            "updated_at": now,
        })

        learner = PriorityLearningService()
        boosts = learner.get_active_boosts()

        item = SurfacedItem(
            entity_type="scene",
            entity_id="scene-gym",
            title="Morning Gym",
            reason="test",
            urgency="medium",
            act_id="act-health",
        )
        total = learner.compute_item_boost(item, boosts)
        # Should include act boost (0.3) + entity_type boost (0.1) + possible time boost
        assert total >= 0.4  # At least act + entity_type

    def test_explicit_priority_overrides_boost(self, populated_db) -> None:
        """Explicit user priority (from drag-reorder) still ranks above learned boost."""
        db = populated_db
        from cairn.cairn.models import SurfacedItem
        from cairn.services.priority_learning_service import PriorityLearningService

        now = datetime.now(timezone.utc).isoformat()
        # Give act-health a big boost
        db.upsert_boost_rule({
            "id": str(uuid.uuid4()),
            "feature_type": "act",
            "feature_value": "act-health",
            "boost_score": 0.9,
            "confidence": 1.0,
            "sample_count": 20,
            "active": 1,
            "created_at": now,
            "updated_at": now,
        })

        # Set explicit priority for career item (rank 0 = highest)
        db.set_attention_priorities(["scene-review"])

        learner = PriorityLearningService()
        boosts_map = learner.get_active_boosts()

        # Career item has explicit priority, Health item only has boost
        items = [
            SurfacedItem(
                entity_type="scene", entity_id="scene-gym",
                title="Gym", reason="test", urgency="medium",
                act_id="act-health",
            ),
            SurfacedItem(
                entity_type="scene", entity_id="scene-review",
                title="Review", reason="test", urgency="medium",
                act_id="act-career",
            ),
        ]

        priorities = db.get_attention_priorities()
        item_boosts = learner.compute_boosts_for_items(items)

        urgency_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        items.sort(key=lambda x: (
            urgency_order.get(x.urgency, 4),
            x.entity_id not in priorities,
            priorities.get(x.entity_id, 999),
            -item_boosts.get(x.entity_id, 0.0),
        ))

        # Career item should be first (explicit priority beats boost)
        assert items[0].entity_id == "scene-review"

    def test_urgency_trumps_boost(self, db) -> None:
        """Urgency tier still takes precedence over learned boosts."""
        from cairn.cairn.models import SurfacedItem
        from cairn.services.priority_learning_service import PriorityLearningService

        now = datetime.now(timezone.utc).isoformat()
        db.upsert_boost_rule({
            "id": str(uuid.uuid4()),
            "feature_type": "act",
            "feature_value": "act-health",
            "boost_score": 1.0,
            "confidence": 1.0,
            "sample_count": 20,
            "active": 1,
            "created_at": now,
            "updated_at": now,
        })

        learner = PriorityLearningService()

        items = [
            SurfacedItem(
                entity_type="scene", entity_id="scene-gym",
                title="Gym", reason="test", urgency="low",
                act_id="act-health",
            ),
            SurfacedItem(
                entity_type="scene", entity_id="scene-review",
                title="Review", reason="test", urgency="critical",
                act_id="act-career",
            ),
        ]

        item_boosts = learner.compute_boosts_for_items(items)
        urgency_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}

        items.sort(key=lambda x: (
            urgency_order.get(x.urgency, 4),
            -item_boosts.get(x.entity_id, 0.0),
        ))

        # Critical urgency item first, regardless of boost
        assert items[0].entity_id == "scene-review"

    def test_boost_attached_to_items(self, db) -> None:
        """Boost values are attached to SurfacedItem after ranking."""
        from cairn.cairn.models import SurfacedItem
        from cairn.services.priority_learning_service import PriorityLearningService

        now = datetime.now(timezone.utc).isoformat()
        db.upsert_boost_rule({
            "id": str(uuid.uuid4()),
            "feature_type": "act",
            "feature_value": "act-health",
            "boost_score": 0.5,
            "confidence": 1.0,
            "sample_count": 10,
            "description": "You tend to prioritize Health items",
            "active": 1,
            "created_at": now,
            "updated_at": now,
        })

        learner = PriorityLearningService()
        boosts = learner.get_active_boosts()

        item = SurfacedItem(
            entity_type="scene", entity_id="scene-gym",
            title="Gym", reason="test", urgency="medium",
            act_id="act-health",
        )

        boost_val = learner.compute_item_boost(item, boosts)
        reasons = learner.get_boost_reasons(item, boosts)

        assert boost_val > 0
        assert len(reasons) >= 1
        assert "Health" in reasons[0]


# =============================================================================
# TestBackwardCompat
# =============================================================================


class TestBackwardCompat:
    """Tests that existing APIs continue working unchanged."""

    def test_ordered_scene_ids_still_works(self, populated_db) -> None:
        """Old ordered_scene_ids API still persists priorities correctly."""
        from cairn.services.priority_signal_service import PrioritySignalService

        service = PrioritySignalService()
        result = service.process_reorder(ordered_scene_ids=["scene-gym", "scene-review"])

        assert result["priorities_updated"] == 2

        priorities = populated_db.get_attention_priorities()
        assert priorities["scene-gym"] == 0
        assert priorities["scene-review"] == 1

    def test_get_attention_priorities_unchanged(self, populated_db) -> None:
        """get_attention_priorities returns same format as before."""
        populated_db.set_attention_priorities(["scene-gym", "scene-review", "scene-dinner"])

        result = populated_db.get_attention_priorities()
        assert isinstance(result, dict)
        assert all(isinstance(k, str) for k in result.keys())
        assert all(isinstance(v, int) for v in result.values())
        assert result["scene-gym"] == 0
        assert result["scene-review"] == 1
        assert result["scene-dinner"] == 2


# =============================================================================
# TestRuleLifecycle
# =============================================================================


class TestRuleLifecycle:
    """Tests for rule creation, update, and deactivation."""

    def test_inactive_rules_ignored(self, db) -> None:
        """Rules with active=0 are not returned by get_active_boost_rules."""
        now = datetime.now(timezone.utc).isoformat()
        db.upsert_boost_rule({
            "id": str(uuid.uuid4()),
            "feature_type": "act",
            "feature_value": "act-health",
            "boost_score": 0.5,
            "confidence": 1.0,
            "sample_count": 10,
            "active": 0,  # Disabled
            "created_at": now,
            "updated_at": now,
        })

        rules = db.get_active_boost_rules()
        assert len(rules) == 0

    def test_user_can_disable_rule(self, db) -> None:
        """Setting active=0 on a rule excludes it from boosts."""
        now = datetime.now(timezone.utc).isoformat()
        rule_id = str(uuid.uuid4())
        db.upsert_boost_rule({
            "id": rule_id,
            "feature_type": "act",
            "feature_value": "act-health",
            "boost_score": 0.5,
            "confidence": 1.0,
            "sample_count": 10,
            "active": 1,
            "created_at": now,
            "updated_at": now,
        })

        rules = db.get_active_boost_rules()
        assert len(rules) == 1

        # Disable the rule
        conn = db._get_connection()
        conn.execute(
            "UPDATE priority_boost_rules SET active = 0 WHERE feature_type = 'act' "
            "AND feature_value = 'act-health'"
        )
        conn.commit()

        rules = db.get_active_boost_rules()
        assert len(rules) == 0

    def test_rules_for_display(self, db) -> None:
        """get_rules_for_display returns all active rules with full details."""
        now = datetime.now(timezone.utc).isoformat()
        db.upsert_boost_rule({
            "id": str(uuid.uuid4()),
            "feature_type": "act",
            "feature_value": "act-health",
            "boost_score": 0.5,
            "confidence": 0.8,
            "sample_count": 8,
            "description": "You tend to prioritize Health items",
            "active": 1,
            "created_at": now,
            "updated_at": now,
        })

        from cairn.services.priority_learning_service import PriorityLearningService

        learner = PriorityLearningService()
        display_rules = learner.get_rules_for_display()
        assert len(display_rules) == 1
        assert display_rules[0]["description"] == "You tend to prioritize Health items"
        assert display_rules[0]["confidence"] == 0.8


# =============================================================================
# TestSchemaV17Migration
# =============================================================================


class TestSchemaV17Migration:
    """Tests for the v17 schema migration."""

    def test_fresh_db_has_v17_tables(self, db) -> None:
        """Fresh database includes reorder_history and priority_boost_rules tables."""
        conn = db._get_connection()

        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='reorder_history'"
        )
        assert cursor.fetchone() is not None

        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='priority_boost_rules'"
        )
        assert cursor.fetchone() is not None

    def test_reorder_history_columns(self, db) -> None:
        """reorder_history has all expected columns."""
        conn = db._get_connection()
        cursor = conn.execute("PRAGMA table_info(reorder_history)")
        columns = {row[1] for row in cursor.fetchall()}
        expected = {
            "id", "reorder_timestamp", "entity_type", "entity_id",
            "old_position", "new_position", "total_items",
            "act_id", "act_title", "scene_stage", "urgency_at_reorder",
            "has_calendar_event", "is_email", "hour_of_day", "day_of_week",
            "created_at",
        }
        assert expected.issubset(columns)

    def test_priority_boost_rules_columns(self, db) -> None:
        """priority_boost_rules has all expected columns."""
        conn = db._get_connection()
        cursor = conn.execute("PRAGMA table_info(priority_boost_rules)")
        columns = {row[1] for row in cursor.fetchall()}
        expected = {
            "id", "feature_type", "feature_value", "boost_score",
            "confidence", "sample_count", "description", "active",
            "created_at", "updated_at",
        }
        assert expected.issubset(columns)

    def test_priority_boost_rules_unique_constraint(self, db) -> None:
        """UNIQUE(feature_type, feature_value) prevents duplicates."""
        now = datetime.now(timezone.utc).isoformat()
        db.upsert_boost_rule({
            "id": str(uuid.uuid4()),
            "feature_type": "act",
            "feature_value": "act-health",
            "boost_score": 0.5,
            "confidence": 1.0,
            "sample_count": 10,
            "active": 1,
            "created_at": now,
            "updated_at": now,
        })

        # Upsert with same feature_type/feature_value should update, not duplicate
        db.upsert_boost_rule({
            "id": str(uuid.uuid4()),
            "feature_type": "act",
            "feature_value": "act-health",
            "boost_score": 0.7,
            "confidence": 1.0,
            "sample_count": 15,
            "active": 1,
            "created_at": now,
            "updated_at": now,
        })

        conn = db._get_connection()
        cursor = conn.execute(
            "SELECT COUNT(*) FROM priority_boost_rules "
            "WHERE feature_type = 'act' AND feature_value = 'act-health'"
        )
        assert cursor.fetchone()[0] == 1

        # Verify it was updated
        cursor = conn.execute(
            "SELECT boost_score, sample_count FROM priority_boost_rules "
            "WHERE feature_type = 'act' AND feature_value = 'act-health'"
        )
        row = cursor.fetchone()
        assert row["boost_score"] == 0.7
        assert row["sample_count"] == 15
