"""Load rich synthetic data into talkingrock.db for UI testing.

Represents a realistic user profile: "Alex Chen", senior platform engineer.

Usage:
    PYTHONPATH=src python scripts/load_synthetic_data.py

The script is idempotent — it checks for existing data before inserting.
Pass --dry-run to see what would be created without writing anything.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime, timedelta
from uuid import uuid4


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(UTC).isoformat()


def _ago(**kwargs: int) -> str:
    """Return an ISO timestamp offset into the past."""
    return (datetime.now(UTC) - timedelta(**kwargs)).isoformat()


def _new_id(prefix: str = "") -> str:
    raw = uuid4().hex[:12]
    return f"{prefix}-{raw}" if prefix else raw


# ---------------------------------------------------------------------------
# Act helpers
# ---------------------------------------------------------------------------

def _ensure_act(
    title: str,
    *,
    act_id: str | None = None,
    notes: str = "",
    color: str | None = None,
    dry_run: bool = False,
) -> str:
    """Return the act_id, creating the act only if it does not already exist."""
    from cairn.play_db import get_act, create_act, _get_connection, _transaction, _now_iso, init_db

    init_db()

    # If a fixed ID is requested (e.g. your-story), check by that ID
    if act_id:
        existing = get_act(act_id)
        if existing:
            print(f"  [exists] Act '{existing['title']}' ({act_id})")
            return act_id
        if dry_run:
            print(f"  [dry-run] Would create Act '{title}' with id={act_id}")
            return act_id
        # Create with the explicit ID via raw SQL so we can pin the ID
        now = _now_iso()
        with _transaction() as conn:
            cursor = conn.execute("SELECT COALESCE(MAX(position), -1) + 1 FROM acts")
            position = cursor.fetchone()[0]
            conn.execute(
                """INSERT INTO acts
                   (act_id, title, active, notes, color, position, created_at, updated_at)
                   VALUES (?, ?, 0, ?, ?, ?, ?, ?)""",
                (act_id, title, notes, color, position, now, now),
            )
        print(f"  [created] Act '{title}' ({act_id})")
        return act_id

    # No fixed ID — check by title
    conn = _get_connection()
    row = conn.execute(
        "SELECT act_id FROM acts WHERE title = ?", (title,)
    ).fetchone()
    if row:
        print(f"  [exists] Act '{title}' ({row['act_id']})")
        return str(row["act_id"])

    if dry_run:
        fake_id = _new_id("act")
        print(f"  [dry-run] Would create Act '{title}'")
        return fake_id

    _, new_act_id = create_act(title=title, notes=notes, color=color)
    print(f"  [created] Act '{title}' ({new_act_id})")
    return new_act_id


def _ensure_scene(
    act_id: str,
    title: str,
    *,
    stage: str = "planning",
    notes: str = "",
    dry_run: bool = False,
) -> str:
    """Return scene_id, creating the scene only if a scene with that title doesn't exist in the act."""
    from cairn.play_db import create_scene, list_scenes

    existing = list_scenes(act_id)
    for s in existing:
        if s["title"] == title:
            print(f"    [exists] Scene '{title}' ({s['scene_id']})")
            return str(s["scene_id"])

    if dry_run:
        fake_id = _new_id("scene")
        print(f"    [dry-run] Would create Scene '{title}' stage={stage}")
        return fake_id

    _, scene_id = create_scene(act_id=act_id, title=title, stage=stage, notes=notes)
    print(f"    [created] Scene '{title}' ({scene_id}) stage={stage}")
    return scene_id


# ---------------------------------------------------------------------------
# Block content helpers (for Your Story rich content)
# ---------------------------------------------------------------------------

def _add_text_block(
    act_id: str,
    parent_block_id: str,
    text: str,
    block_type: str = "paragraph",
    *,
    dry_run: bool = False,
) -> str | None:
    """Append a text block as a child of parent_block_id. Returns block id."""
    if dry_run:
        print(f"      [dry-run] Would add {block_type} block: {text[:60]!r}")
        return None

    from cairn.play.blocks_db import create_block, get_block
    from cairn.play_db import get_act

    block = create_block(
        type=block_type,
        act_id=act_id,
        parent_id=parent_block_id,
        rich_text=[{"content": text, "position": 0}],
    )
    return block.id


def _setup_your_story_blocks(act_id: str, root_block_id: str, *, dry_run: bool) -> None:
    """Populate Your Story with identity, priorities, and working-style blocks."""
    from cairn.play.blocks_db import create_block, get_block
    from cairn.play_db import _get_connection

    conn = _get_connection()

    # Check if content already exists (any children of the root block)
    existing = conn.execute(
        "SELECT COUNT(*) FROM blocks WHERE parent_id = ?", (root_block_id,)
    ).fetchone()[0]

    if existing > 0:
        print(f"  [exists] Your Story blocks already populated ({existing} child blocks)")
        return

    if dry_run:
        print("  [dry-run] Would populate Your Story with identity/priorities/working-style blocks")
        return

    sections = [
        ("heading_1", "Identity"),
        ("paragraph", "Alex Chen, senior platform engineer at a growing startup. Values deep work, family time, and staying physically active."),
        ("heading_1", "Priorities"),
        ("bulleted_list", "Ship the Q2 platform migration — critical for company infrastructure"),
        ("bulleted_list", "Train for a half marathon — race is in late spring"),
        ("bulleted_list", "Be present for kids' school events — especially Tuesday mornings"),
        ("heading_1", "Working Style"),
        ("bulleted_list", "Prefers focused 2-hour deep-work blocks with no interruptions"),
        ("bulleted_list", "Async communication preferred — responds within 4 hours during work hours"),
        ("bulleted_list", "Weekly planning sessions every Monday morning to set priorities"),
        ("bulleted_list", "Bullet-point summaries land better than long paragraphs"),
    ]

    for block_type, text in sections:
        block = create_block(
            type=block_type,
            act_id=act_id,
            parent_id=root_block_id,
            rich_text=[{"content": text, "position": 0}],
        )
        print(f"    [created] {block_type} block: {text[:60]!r}")


# ---------------------------------------------------------------------------
# Conversation helpers (raw SQL — bypasses singleton & state-machine so we
# can write pre-existing historical/archived data without going through the
# full active→ready_to_close→compressing→archived pipeline)
# ---------------------------------------------------------------------------

def _ensure_conversation(
    title_hint: str,
    messages: list[dict],
    *,
    dry_run: bool = False,
) -> str | None:
    """Create an archived conversation with the given messages if not already present."""
    from cairn.play_db import (
        ARCHIVED_CONVERSATIONS_ACT_ID,
        _get_connection,
        _transaction,
        _now_iso,
        init_db,
    )

    init_db()
    conn = _get_connection()

    # Check for existing conversation with a matching first user message
    first_user = next((m["content"] for m in messages if m["role"] == "user"), "")
    if first_user:
        # Look for a message row with this content
        row = conn.execute(
            "SELECT conversation_id FROM messages WHERE content = ? LIMIT 1",
            (first_user,),
        ).fetchone()
        if row:
            conv_id = row["conversation_id"]
            print(f"  [exists] Conversation '{title_hint}' ({conv_id})")
            return str(conv_id)

    if dry_run:
        print(f"  [dry-run] Would create archived conversation '{title_hint}' ({len(messages)} messages)")
        return None

    conv_id = _new_id()
    conv_block_id = f"block-{_new_id()}"
    started_at = _ago(days=7)
    archived_at = _ago(days=6)
    now = _now_iso()

    with _transaction() as conn2:
        # Block for the conversation
        conn2.execute(
            """INSERT INTO blocks (id, type, act_id, parent_id, page_id, scene_id,
               position, created_at, updated_at)
               VALUES (?, 'conversation', ?, NULL, NULL, NULL, 0, ?, ?)""",
            (conv_block_id, ARCHIVED_CONVERSATIONS_ACT_ID, started_at, archived_at),
        )

        # Conversation row — directly archived
        conn2.execute(
            """INSERT INTO conversations
               (id, block_id, status, started_at, last_message_at,
                closed_at, archived_at, message_count, is_paused)
               VALUES (?, ?, 'archived', ?, ?, ?, ?, ?, 0)""",
            (
                conv_id,
                conv_block_id,
                started_at,
                archived_at,
                archived_at,
                archived_at,
                len(messages),
            ),
        )

        # Messages
        for position, msg in enumerate(messages):
            msg_id = _new_id()
            msg_block_id = f"block-{_new_id()}"
            msg_time = (
                datetime.fromisoformat(started_at) + timedelta(minutes=position * 3)
            ).isoformat()

            conn2.execute(
                """INSERT INTO blocks (id, type, act_id, parent_id, page_id, scene_id,
                   position, created_at, updated_at)
                   VALUES (?, 'message', ?, ?, NULL, NULL, ?, ?, ?)""",
                (
                    msg_block_id,
                    ARCHIVED_CONVERSATIONS_ACT_ID,
                    conv_block_id,
                    position,
                    msg_time,
                    msg_time,
                ),
            )

            conn2.execute(
                """INSERT INTO messages
                   (id, conversation_id, block_id, role, content, position,
                    created_at, active_act_id, active_scene_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL)""",
                (
                    msg_id,
                    conv_id,
                    msg_block_id,
                    msg["role"],
                    msg["content"],
                    position,
                    msg_time,
                ),
            )

    print(f"  [created] Archived conversation '{title_hint}' ({conv_id}, {len(messages)} messages)")
    return conv_id


# ---------------------------------------------------------------------------
# Memory helpers
# ---------------------------------------------------------------------------

def _ensure_memory(
    narrative: str,
    *,
    memory_type: str,
    conversation_id: str,
    destination_act_id: str | None = None,
    dry_run: bool = False,
) -> str | None:
    """Create an approved memory if one with this narrative does not exist."""
    from cairn.play_db import (
        YOUR_STORY_ACT_ID,
        _get_connection,
        _transaction,
        _now_iso,
        ensure_memories_page,
        init_db,
    )

    init_db()
    conn = _get_connection()

    # Check if a memory with this exact narrative already exists
    row = conn.execute(
        "SELECT id FROM memories WHERE narrative = ? LIMIT 1", (narrative,)
    ).fetchone()
    if row:
        print(f"  [exists] Memory: {narrative[:70]!r}")
        return str(row["id"])

    if dry_run:
        print(f"  [dry-run] Would create {memory_type} memory: {narrative[:70]!r}")
        return None

    act_id = destination_act_id or YOUR_STORY_ACT_ID
    is_your_story = destination_act_id is None
    memory_id = _new_id()
    block_id = f"block-{_new_id()}"
    memories_page_id = ensure_memories_page(act_id)
    now = _now_iso()

    # Auto-approve types: fact, preference, relationship (mirrors memory_service logic)
    auto_approve = memory_type in {"fact", "preference", "relationship"}
    status = "approved" if auto_approve else "pending_review"

    with _transaction() as conn2:
        conn2.execute(
            """INSERT INTO blocks (id, type, act_id, parent_id, page_id, scene_id,
               position, created_at, updated_at)
               VALUES (?, 'memory', ?, NULL, ?, NULL, 0, ?, ?)""",
            (block_id, act_id, memories_page_id, now, now),
        )

        conn2.execute(
            """INSERT INTO memories
               (id, block_id, conversation_id, narrative,
                destination_act_id, is_your_story, status,
                extraction_model, extraction_confidence, signal_count,
                source, memory_type, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, '', 0.9, 1, 'turn_assessment', ?, ?)""",
            (
                memory_id,
                block_id,
                conversation_id,
                narrative,
                destination_act_id,
                1 if is_your_story else 0,
                status,
                memory_type,
                now,
            ),
        )

        # For commitment/priority types not auto-approved, explicitly set approved
        if not auto_approve:
            conn2.execute(
                "UPDATE memories SET status = 'approved', user_reviewed = 1 WHERE id = ?",
                (memory_id,),
            )

    print(f"  [created] {memory_type} memory ({status}): {narrative[:70]!r}")
    return memory_id


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(dry_run: bool = False) -> None:
    from cairn.play_db import (
        init_db,
        ensure_your_story_act,
        YOUR_STORY_ACT_ID,
        get_act,
        set_act_root_block,
        create_act_with_root_block,
    )
    from cairn.play.blocks_db import create_block

    init_db()

    print("=" * 60)
    print("Loading synthetic data for Alex Chen")
    print(f"{'(DRY RUN — no writes)' if dry_run else '(writing to talkingrock.db)'}")
    print("=" * 60)

    # ------------------------------------------------------------------
    # 1. Your Story — ensure exists, populate blocks
    # ------------------------------------------------------------------
    print("\n[1] Your Story Act")
    acts, your_story_id = ensure_your_story_act()
    act = get_act(your_story_id)

    if not act:
        print("  ERROR: Could not find or create Your Story act.")
        sys.exit(1)

    root_block_id = act.get("root_block_id")
    if not root_block_id:
        if dry_run:
            print("  [dry-run] Would create root block for Your Story")
            root_block_id = "dry-run-root"
        else:
            root_block = create_block(
                type="page",
                act_id=your_story_id,
                properties={"title": "Your Story"},
            )
            root_block_id = root_block.id
            set_act_root_block(your_story_id, root_block_id)
            print(f"  [created] Root block for Your Story ({root_block_id})")

    _setup_your_story_blocks(your_story_id, root_block_id, dry_run=dry_run)

    # ------------------------------------------------------------------
    # 2. Career Growth Act + Scenes
    # ------------------------------------------------------------------
    print("\n[2] Career Growth Act")
    career_act_id = _ensure_act(
        "Career Growth",
        notes="Professional development, engineering leadership, and Q2 deliverables.",
        color="#4A90E2",
        dry_run=dry_run,
    )

    career_scenes = [
        ("Q2 Platform Migration", "in_progress",
         "Critical migration to new infrastructure. Must maintain backward compatibility for 2+ weeks."),
        ("Tech Lead Mentoring", "in_progress",
         "Weekly 1:1s with two junior engineers. Focus on system design and code review skills."),
        ("Architecture Review Board", "planning",
         "Monthly ARB meeting. Next agenda: service mesh proposal and database sharding strategy."),
    ]

    print("  Scenes:")
    for title, stage, notes in career_scenes:
        _ensure_scene(career_act_id, title, stage=stage, notes=notes, dry_run=dry_run)

    # ------------------------------------------------------------------
    # 3. Health & Fitness Act + Scenes
    # ------------------------------------------------------------------
    print("\n[3] Health & Fitness Act")
    health_act_id = _ensure_act(
        "Health & Fitness",
        notes="Physical wellness: running, nutrition, and recovery.",
        color="#7ED321",
        dry_run=dry_run,
    )

    health_scenes = [
        ("Half Marathon Training", "in_progress",
         "16-week plan. Currently in week 8. Long run on Sundays, tempo on Tuesdays/Thursdays."),
        ("Weekly Meal Prep", "complete",
         "Sunday prep: proteins, grains, and veggies for the week. Saves ~45 min daily."),
        ("Sleep Optimization", "planning",
         "Target 7.5 hrs/night. Experimenting with earlier wind-down (no screens after 9:30pm)."),
    ]

    print("  Scenes:")
    for title, stage, notes in health_scenes:
        _ensure_scene(health_act_id, title, stage=stage, notes=notes, dry_run=dry_run)

    # ------------------------------------------------------------------
    # 4. Family Act + Scenes
    # ------------------------------------------------------------------
    print("\n[4] Family Act")
    family_act_id = _ensure_act(
        "Family",
        notes="Family priorities, school involvement, home projects.",
        color="#F5A623",
        dry_run=dry_run,
    )

    family_scenes = [
        ("Kids' Spring Activities", "in_progress",
         "Soccer Tuesdays 4-5:30pm, swimming Saturdays 9am. Calendar blockers in place."),
        ("Summer Vacation Planning", "planning",
         "Considering Pacific Northwest road trip in late July. Need to book by end of April."),
        ("Home Office Renovation", "awaiting_data",
         "Waiting on contractor quotes. Three bids requested, two received so far."),
    ]

    print("  Scenes:")
    for title, stage, notes in family_scenes:
        _ensure_scene(family_act_id, title, stage=stage, notes=notes, dry_run=dry_run)

    # ------------------------------------------------------------------
    # 5. Archived Conversations
    # ------------------------------------------------------------------
    print("\n[5] Archived Conversations")

    conv1_id = _ensure_conversation(
        "Q2 Migration Planning",
        messages=[
            {
                "role": "user",
                "content": "I'm trying to figure out the safest rollout strategy for the Q2 platform migration. We have a bunch of downstream services that depend on the current API.",
            },
            {
                "role": "cairn",
                "content": "Given the downstream dependencies, a gradual rollout with backward compatibility makes the most sense. How long do you realistically need to keep the old API endpoints alive in parallel?",
            },
            {
                "role": "user",
                "content": "At minimum two weeks. Some teams have slow release cycles. I'm leaning toward a feature flag approach rather than a big-bang cutover.",
            },
            {
                "role": "cairn",
                "content": "Feature flags are the right call here — they give you per-team control and a clean kill switch if something goes wrong. The two-week backward compatibility window is a concrete constraint worth recording.",
            },
            {
                "role": "user",
                "content": "Yeah, let's go with gradual rollout. I'll document the two-week compatibility requirement in the migration spec.",
            },
        ],
        dry_run=dry_run,
    )

    conv2_id = _ensure_conversation(
        "Morning Routine & Energy",
        messages=[
            {
                "role": "user",
                "content": "I've been trying to figure out the best time for my runs. Evening runs leave me wired and I can't sleep.",
            },
            {
                "role": "cairn",
                "content": "That tracks — vigorous exercise raises core temperature and cortisol, both of which delay sleep onset. What does your morning window look like?",
            },
            {
                "role": "user",
                "content": "I'm up around 6am. If I run before 7 I feel great all day. After 7 the day gets chaotic and I end up skipping.",
            },
            {
                "role": "cairn",
                "content": "There's a clear pattern there: pre-7am runs correlate with better energy and consistency. Worth treating that as a hard constraint rather than a preference.",
            },
        ],
        dry_run=dry_run,
    )

    conv3_id = _ensure_conversation(
        "Weekly Schedule Conflicts",
        messages=[
            {
                "role": "user",
                "content": "My team standup is at 9:30am on Tuesdays but that's exactly when I do school drop-off for the kids. I keep showing up late.",
            },
            {
                "role": "cairn",
                "content": "That's a recurring conflict with a predictable cost. Have you floated moving the standup, or is Tuesday 9:30 fixed for the whole team?",
            },
            {
                "role": "user",
                "content": "It's been fixed for months. I should just block it on my calendar and ask the team to shift it by 30 minutes.",
            },
            {
                "role": "cairn",
                "content": "That seems like the right move. A 30-minute shift is a small ask and removes a recurring source of stress.",
            },
        ],
        dry_run=dry_run,
    )

    # Use a fallback conv_id for memories if dry_run produced no real IDs
    fallback_conv_id = conv1_id or FALLBACK_CONV_ID

    # ------------------------------------------------------------------
    # 6. Approved Memories
    # ------------------------------------------------------------------
    print("\n[6] Memories")

    memories = [
        # (narrative, memory_type, conversation_id, destination_act_id)
        (
            "The Q2 migration needs to support backward compatibility for at least 2 weeks to accommodate teams with slow release cycles.",
            "fact",
            conv1_id,
            career_act_id,
        ),
        (
            "Decided to use gradual rollout with feature flags instead of big-bang deployment for the Q2 platform migration.",
            "commitment",
            conv1_id,
            career_act_id,
        ),
        (
            "Prefers morning runs before 7am — energy levels are noticeably better and the workout is more likely to happen.",
            "preference",
            conv2_id,
            health_act_id,
        ),
        (
            "Team standup at 9:30am on Tuesdays conflicts with kids' school drop-off — recurring schedule tension.",
            "fact",
            conv3_id,
            None,  # Your Story — cross-cutting
        ),
        (
            "Alex responds better to bullet-point summaries than long paragraphs when reviewing decisions or plans.",
            "preference",
            conv3_id,
            None,  # Your Story
        ),
    ]

    for narrative, memory_type, conv_id, dest_act_id in memories:
        # If dry_run returned no conv_id, we still print; skip actual write
        effective_conv_id = conv_id or "synthetic-placeholder"
        _ensure_memory(
            narrative,
            memory_type=memory_type,
            conversation_id=effective_conv_id,
            destination_act_id=dest_act_id,
            dry_run=dry_run,
        )

    # ------------------------------------------------------------------
    # 7. Attention Priorities (scene ordering)
    # ------------------------------------------------------------------
    print("\n[7] Attention Priorities")

    if dry_run:
        print("  [dry-run] Would set attention priorities for high-signal scenes")
    else:
        from cairn.play_db import get_attention_priorities, set_attention_priorities, list_scenes

        existing_priorities = get_attention_priorities()
        if existing_priorities:
            print(f"  [exists] Attention priorities already set ({len(existing_priorities)} items)")
        else:
            # Pull scene IDs we want to prioritize
            career_scenes_list = list_scenes(career_act_id)
            health_scenes_list = list_scenes(health_act_id)
            family_scenes_list = list_scenes(family_act_id)

            # Find specific scenes by title
            def find_scene_id(scenes: list, title: str) -> str | None:
                for s in scenes:
                    if s["title"] == title:
                        return s["scene_id"]
                return None

            priority_order = [
                sid for sid in [
                    find_scene_id(career_scenes_list, "Q2 Platform Migration"),
                    find_scene_id(health_scenes_list, "Half Marathon Training"),
                    find_scene_id(family_scenes_list, "Kids' Spring Activities"),
                    find_scene_id(career_scenes_list, "Tech Lead Mentoring"),
                    find_scene_id(family_scenes_list, "Summer Vacation Planning"),
                    find_scene_id(career_scenes_list, "Architecture Review Board"),
                    find_scene_id(family_scenes_list, "Home Office Renovation"),
                    find_scene_id(health_scenes_list, "Sleep Optimization"),
                ] if sid is not None
            ]

            set_attention_priorities(priority_order)
            print(f"  [created] Set attention priorities for {len(priority_order)} scenes")
            for i, sid in enumerate(priority_order):
                print(f"    {i}: {sid}")

    # ------------------------------------------------------------------
    # Done
    # ------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("Synthetic data load complete.")
    print("  Acts:          Your Story, Career Growth, Health & Fitness, Family")
    print("  Scenes:        9 total across 3 acts")
    print("  Conversations: 3 archived (Q2 Migration, Morning Routine, Schedule)")
    print("  Memories:      5 approved (2 facts, 2 preferences, 1 commitment)")
    print("  Priorities:    Scene ordering set in attention_priorities")
    print("=" * 60)


# Fallback for dry-run when no real conversation IDs are generated
FALLBACK_CONV_ID = "synthetic-placeholder"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be created without writing to the database.",
    )
    args = parser.parse_args()
    main(dry_run=args.dry_run)
