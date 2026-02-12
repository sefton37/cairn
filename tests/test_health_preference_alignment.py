"""Tests for Preference Alignment health check.

Run with: PYTHONPATH=src pytest tests/test_health_preference_alignment.py -v --no-cov
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from reos.cairn.health.checks.preference_alignment import PreferenceAlignmentCheck
from reos.cairn.health.runner import Severity
from reos.cairn.store import CairnStore


@pytest.fixture
def store(tmp_path: Path) -> CairnStore:
    """Create a fresh CairnStore."""
    db_path = tmp_path / "cairn.db"
    return CairnStore(db_path)


def test_no_prioritized_items_returns_healthy(store: CairnStore):
    """With no prioritized items, check should return healthy."""
    check = PreferenceAlignmentCheck(store)
    results = check.run()

    assert len(results) == 1
    assert results[0].severity == Severity.HEALTHY
    assert "No prioritized items" in results[0].title
    assert results[0].finding_key == "preference_alignment:no_priorities"


def test_high_priority_with_recent_activity_returns_healthy(store: CairnStore):
    """High-priority items with recent activity should return healthy."""
    check = PreferenceAlignmentCheck(store)

    # Create two high-priority acts with recent activity
    store.set_priority("act", "act-1", priority=5, reason="Important")
    store.set_priority("act", "act-2", priority=4, reason="Also important")

    # Touch them recently (within 14 days)
    store.touch("act", "act-1")
    store.touch("act", "act-2")

    results = check.run()

    assert len(results) == 1
    assert results[0].severity == Severity.HEALTHY
    assert "align with activity" in results[0].title.lower()
    assert results[0].finding_key == "preference_alignment:aligned"


def test_high_priority_no_recent_activity_returns_warning(store: CairnStore):
    """High-priority items without recent activity (14+ days) should return warning."""
    check = PreferenceAlignmentCheck(store)

    # Create a high-priority act
    store.set_priority("act", "act-stale", priority=5, reason="Important but neglected")

    # Manually set last_touched to 20 days ago
    twenty_days_ago = (datetime.now() - timedelta(days=20)).isoformat()
    conn = store._get_connection()
    conn.execute(
        "UPDATE cairn_metadata SET last_touched = ? WHERE entity_id = ?",
        (twenty_days_ago, "act-stale"),
    )
    conn.commit()
    conn.close()

    results = check.run()

    assert len(results) == 1
    assert results[0].severity == Severity.WARNING
    assert "1 high-priority item(s) haven't seen activity" in results[0].title
    assert "priority 4-5" in results[0].details
    assert "14+ days" in results[0].details
    assert "ready when you are" in results[0].details.lower()
    # Implementation truncates to 8 chars
    assert "act-stal" in results[0].details
    assert results[0].finding_key == "preference_alignment:misaligned:1"


def test_multiple_misaligned_items(store: CairnStore):
    """Multiple high-priority items without activity should all be reported."""
    check = PreferenceAlignmentCheck(store)

    # Create three high-priority acts
    store.set_priority("act", "act-stale-1", priority=5)
    store.set_priority("act", "act-stale-2", priority=4)
    store.set_priority("act", "act-stale-3", priority=5)

    # Set all to 20 days ago
    twenty_days_ago = (datetime.now() - timedelta(days=20)).isoformat()
    conn = store._get_connection()
    for i in range(1, 4):
        conn.execute(
            "UPDATE cairn_metadata SET last_touched = ? WHERE entity_id = ?",
            (twenty_days_ago, f"act-stale-{i}"),
        )
    conn.commit()
    conn.close()

    results = check.run()

    assert len(results) == 1
    assert results[0].severity == Severity.WARNING
    assert "3 high-priority item(s) haven't seen activity" in results[0].title
    # All three should be listed in details
    assert "act-stal" in results[0].details
    assert "priority 5" in results[0].details
    assert "priority 4" in results[0].details
    assert results[0].finding_key == "preference_alignment:misaligned:3"


def test_mix_of_aligned_and_misaligned(store: CairnStore):
    """Mix of aligned and misaligned high-priority items should report only misaligned."""
    check = PreferenceAlignmentCheck(store)

    # Create one fresh high-priority act
    store.set_priority("act", "act-fresh", priority=5)
    store.touch("act", "act-fresh")

    # Create two stale high-priority acts
    store.set_priority("act", "act-stale-1", priority=4)
    store.set_priority("act", "act-stale-2", priority=5)

    twenty_days_ago = (datetime.now() - timedelta(days=20)).isoformat()
    conn = store._get_connection()
    conn.execute(
        "UPDATE cairn_metadata SET last_touched = ? WHERE entity_id = ?",
        (twenty_days_ago, "act-stale-1"),
    )
    conn.execute(
        "UPDATE cairn_metadata SET last_touched = ? WHERE entity_id = ?",
        (twenty_days_ago, "act-stale-2"),
    )
    conn.commit()
    conn.close()

    results = check.run()

    assert len(results) == 1
    assert results[0].severity == Severity.WARNING
    assert "2 high-priority item(s) haven't seen activity" in results[0].title
    # Only stale ones should be mentioned
    assert "act-stal" in results[0].details
    # Fresh one should NOT be mentioned
    assert "act-fres" not in results[0].details


def test_priority_exactly_at_threshold(store: CairnStore):
    """Priority exactly 4 should be checked (threshold is >=4)."""
    check = PreferenceAlignmentCheck(store)

    # Create act with priority exactly 4
    store.set_priority("act", "act-threshold", priority=4)

    # Set to 20 days ago
    twenty_days_ago = (datetime.now() - timedelta(days=20)).isoformat()
    conn = store._get_connection()
    conn.execute(
        "UPDATE cairn_metadata SET last_touched = ? WHERE entity_id = ?",
        (twenty_days_ago, "act-threshold"),
    )
    conn.commit()
    conn.close()

    results = check.run()

    assert len(results) == 1
    assert results[0].severity == Severity.WARNING
    assert "1 high-priority item(s)" in results[0].title


def test_priority_below_threshold_ignored(store: CairnStore):
    """Priority <4 should be ignored even if stale."""
    check = PreferenceAlignmentCheck(store)

    # Create acts with priority 1, 2, 3 (below threshold)
    store.set_priority("act", "act-low-1", priority=1)
    store.set_priority("act", "act-low-2", priority=2)
    store.set_priority("act", "act-low-3", priority=3)

    # Set all to 30 days ago
    thirty_days_ago = (datetime.now() - timedelta(days=30)).isoformat()
    conn = store._get_connection()
    for i in range(1, 4):
        conn.execute(
            "UPDATE cairn_metadata SET last_touched = ? WHERE entity_id = ?",
            (thirty_days_ago, f"act-low-{i}"),
        )
    conn.commit()
    conn.close()

    results = check.run()

    # Should return aligned since no priority >=4 items are stale
    assert len(results) == 1
    assert results[0].severity == Severity.HEALTHY
    assert "align with activity" in results[0].title.lower()


def test_exactly_14_days_stale_is_misaligned(store: CairnStore):
    """Exactly 14 days since last touch should be considered misaligned."""
    check = PreferenceAlignmentCheck(store)

    store.set_priority("act", "act-threshold", priority=5)

    # Set to exactly 14 days ago
    fourteen_days_ago = (datetime.now() - timedelta(days=14)).isoformat()
    conn = store._get_connection()
    conn.execute(
        "UPDATE cairn_metadata SET last_touched = ? WHERE entity_id = ?",
        (fourteen_days_ago, "act-threshold"),
    )
    conn.commit()
    conn.close()

    results = check.run()

    assert len(results) == 1
    assert results[0].severity == Severity.WARNING


def test_13_days_stale_is_aligned(store: CairnStore):
    """13 days since last touch should still be considered aligned (<14 days)."""
    check = PreferenceAlignmentCheck(store)

    store.set_priority("act", "act-recent", priority=5)

    # Set to 13 days ago
    thirteen_days_ago = (datetime.now() - timedelta(days=13)).isoformat()
    conn = store._get_connection()
    conn.execute(
        "UPDATE cairn_metadata SET last_touched = ? WHERE entity_id = ?",
        (thirteen_days_ago, "act-recent"),
    )
    conn.commit()
    conn.close()

    results = check.run()

    assert len(results) == 1
    assert results[0].severity == Severity.HEALTHY
    assert "align with activity" in results[0].title.lower()


def test_null_last_touched_is_misaligned(store: CairnStore):
    """Items with NULL last_touched should be considered misaligned."""
    check = PreferenceAlignmentCheck(store)

    # Create metadata with priority but NULL last_touched
    conn = store._get_connection()
    conn.execute(
        """
        INSERT INTO cairn_metadata (entity_type, entity_id, priority, last_touched, touch_count)
        VALUES ('act', 'act-never-touched', 5, NULL, 0)
        """
    )
    conn.commit()
    conn.close()

    results = check.run()

    assert len(results) == 1
    assert results[0].severity == Severity.WARNING
    assert "1 high-priority item(s) haven't seen activity" in results[0].title


def test_checks_all_entity_types(store: CairnStore):
    """Check should work with any entity type (act, scene, etc)."""
    check = PreferenceAlignmentCheck(store)

    # Create high-priority scene
    store.set_priority("scene", "scene-stale", priority=4)

    twenty_days_ago = (datetime.now() - timedelta(days=20)).isoformat()
    conn = store._get_connection()
    conn.execute(
        "UPDATE cairn_metadata SET last_touched = ? WHERE entity_id = ?",
        (twenty_days_ago, "scene-stale"),
    )
    conn.commit()
    conn.close()

    results = check.run()

    assert len(results) == 1
    assert results[0].severity == Severity.WARNING
    assert "scene scene-st" in results[0].details  # Shows entity_type (truncated to 8 chars)


def test_reframe_protocol_language(store: CairnStore):
    """Check should use Reframe Protocol language (non-blaming)."""
    check = PreferenceAlignmentCheck(store)

    store.set_priority("act", "act-stale", priority=5)

    twenty_days_ago = (datetime.now() - timedelta(days=20)).isoformat()
    conn = store._get_connection()
    conn.execute(
        "UPDATE cairn_metadata SET last_touched = ? WHERE entity_id = ?",
        (twenty_days_ago, "act-stale"),
    )
    conn.commit()
    conn.close()

    results = check.run()

    # Should frame as neutral observation, not blame
    assert "ready when you are" in results[0].details.lower()
    # Should NOT contain blaming language
    assert "you should" not in results[0].details.lower()
    assert "you need to" not in results[0].details.lower()
    assert "you forgot" not in results[0].details.lower()
