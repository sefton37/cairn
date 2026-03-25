"""Core generator: takes profile data and produces a talkingrock.db."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from .schema import SCHEMA_SQL

BASE_DATE = datetime(2026, 3, 13, 9, 0, 0)


def uid(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4()}"


def iso(dt: datetime | None = None) -> str:
    return (dt or BASE_DATE).isoformat()


def create_database(db_path: str) -> sqlite3.Connection:
    """Create a new profile database with full schema."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()

    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    return conn


def _make_block(conn, block_type, act_id, page_id=None, scene_id=None,
                parent_id=None, position=0, ts=None):
    """Create a block and return its ID."""
    block_id = uid("block-")
    conn.execute(
        """INSERT INTO blocks (id, type, parent_id, act_id, page_id, scene_id,
           position, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (block_id, block_type, parent_id, act_id, page_id, scene_id,
         position, iso(ts), iso(ts)),
    )
    return block_id


def _make_rich_text(conn, block_id, content, position=0):
    """Create a rich_text entry for a block."""
    rt_id = uid("rt-")
    conn.execute(
        """INSERT INTO rich_text (id, block_id, position, content)
           VALUES (?, ?, ?, ?)""",
        (rt_id, block_id, position, content),
    )
    return rt_id


def generate_system_acts(conn):
    """Create the two system acts: your-story and archived-conversations."""
    now = iso()
    for act_id, title, role in [
        ("your-story", "Your Story", "your_story"),
        ("archived-conversations", "Archived Conversations", "archived_conversations"),
    ]:
        # Create act first (block FK requires act to exist)
        conn.execute(
            """INSERT INTO acts (act_id, title, active, notes, color, system_role,
               root_block_id, position, created_at, updated_at)
               VALUES (?, ?, 0, '', NULL, ?, NULL, 0, ?, ?)""",
            (act_id, title, role, now, now),
        )
        # Now create root block and link it
        root_block = _make_block(conn, "act_root", act_id, ts=BASE_DATE)
        conn.execute(
            "UPDATE acts SET root_block_id = ? WHERE act_id = ?",
            (root_block, act_id),
        )
    conn.commit()


def generate_your_story(conn, profile: dict):
    """Populate the Your Story act with the profile's bio."""
    act_id = "your-story"
    now = iso()

    # Create a page under Your Story
    page_id = uid("page-")
    conn.execute(
        """INSERT INTO pages (page_id, act_id, parent_page_id, title, icon,
           position, created_at, updated_at)
           VALUES (?, ?, NULL, ?, '📋', 0, ?, ?)""",
        (page_id, act_id, "About Me", now, now),
    )

    # Create text blocks for the bio
    story = profile["your_story"]
    paragraphs = [p.strip() for p in story.split("\n\n") if p.strip()]
    for i, para in enumerate(paragraphs):
        block_id = _make_block(conn, "paragraph", act_id, page_id=page_id,
                               position=i, ts=BASE_DATE)
        _make_rich_text(conn, block_id, para, position=0)

    conn.commit()


def generate_acts(conn, profile: dict) -> list[dict]:
    """Generate user acts with scenes. Returns list of act dicts with IDs."""
    now = iso()
    result = []

    for i, act in enumerate(profile["acts"]):
        act_id = uid("act-")

        # Create act first (block FK requires act), then root block, then link
        conn.execute(
            """INSERT INTO acts (act_id, title, active, notes, color,
               root_block_id, position, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, NULL, ?, ?, ?)""",
            (act_id, act["title"], 1 if i == 0 else 0, act["notes"],
             act.get("color", "#6366f1"), i + 1, now, now),
        )
        root_block = _make_block(conn, "act_root", act_id, ts=BASE_DATE)
        conn.execute(
            "UPDATE acts SET root_block_id = ? WHERE act_id = ?",
            (root_block, act_id),
        )

        # Create a notes page for the act
        page_id = uid("page-")
        conn.execute(
            """INSERT INTO pages (page_id, act_id, parent_page_id, title, icon,
               position, created_at, updated_at)
               VALUES (?, ?, NULL, ?, '📝', 0, ?, ?)""",
            (page_id, act_id, f"{act['title']} Notes", now, now),
        )

        # Add act description as blocks on the notes page
        for j, para in enumerate(act["notes"].split("\n\n")[:5]):
            if para.strip():
                block_id = _make_block(conn, "paragraph", act_id,
                                       page_id=page_id, position=j, ts=BASE_DATE)
                _make_rich_text(conn, block_id, para.strip())

        # Generate scenes
        scene_ids = []
        for s_i, scene in enumerate(act.get("scenes", [])):
            scene_id = uid("scene-")
            conn.execute(
                """INSERT INTO scenes (scene_id, act_id, title, stage, notes,
                   position, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (scene_id, act_id, scene["title"], scene.get("stage", "planning"),
                 scene.get("notes", ""), s_i, now, now),
            )
            scene_ids.append(scene_id)

            # Add cairn_metadata for each scene
            conn.execute(
                """INSERT INTO cairn_metadata (entity_type, entity_id,
                   last_touched, touch_count, created_at, kanban_state)
                   VALUES ('scene', ?, ?, ?, ?, ?)""",
                (scene_id, now, s_i + 1, now,
                 {"planning": "backlog", "in_progress": "active",
                  "awaiting_data": "blocked", "complete": "done"}.get(
                     scene.get("stage", "planning"), "backlog")),
            )

        result.append({"act_id": act_id, "title": act["title"],
                        "scene_ids": scene_ids, "page_id": page_id})

    conn.commit()
    return result


def generate_conversations(conn, profile: dict, acts: list[dict]):
    """Generate archived conversations with messages."""
    conv_act = "archived-conversations"

    for c_i, conv in enumerate(profile.get("conversations", [])):
        conv_ts = BASE_DATE - timedelta(days=30 - c_i * 7, hours=c_i * 2)

        # Create block for conversation
        conv_block = _make_block(conn, "conversation", conv_act, ts=conv_ts)

        conv_id = uid("conv-")
        messages = conv.get("messages", [])
        msg_count = len(messages)
        last_msg_ts = conv_ts + timedelta(minutes=msg_count * 2)

        conn.execute(
            """INSERT INTO conversations (id, block_id, status, started_at,
               last_message_at, archived_at, message_count, is_paused)
               VALUES (?, ?, 'archived', ?, ?, ?, ?, 0)""",
            (conv_id, conv_block, iso(conv_ts), iso(last_msg_ts),
             iso(last_msg_ts), msg_count),
        )

        # Create messages
        for m_i, msg in enumerate(messages):
            msg_ts = conv_ts + timedelta(minutes=m_i * 2)
            msg_block = _make_block(conn, "message", conv_act, ts=msg_ts)
            msg_id = uid("msg-")

            role = msg["role"]
            if role == "assistant":
                role = "cairn"

            conn.execute(
                """INSERT INTO messages (id, conversation_id, block_id, role,
                   content, position, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (msg_id, conv_id, msg_block, role, msg["content"],
                 m_i, iso(msg_ts)),
            )

        # Create conversation summary
        first_user_msg = next(
            (m["content"] for m in messages if m["role"] == "user"), "")
        summary_text = f"User discussed: {first_user_msg[:100]}..."
        conn.execute(
            """INSERT INTO conversation_summaries (id, conversation_id,
               summary, summary_model, created_at, updated_at)
               VALUES (?, ?, ?, 'test-gen', ?, ?)""",
            (uid("summary-"), conv_id, summary_text, iso(conv_ts), iso(conv_ts)),
        )

    conn.commit()


def generate_memories(conn, profile: dict, acts: list[dict]):
    """Generate memories from conversations."""
    # Need at least one conversation to link memories to
    conv_row = conn.execute(
        "SELECT id FROM conversations LIMIT 1"
    ).fetchone()
    if not conv_row:
        return

    conv_id = conv_row[0]
    conv_act = "archived-conversations"

    for m_i, mem in enumerate(profile.get("memories", [])):
        mem_ts = BASE_DATE - timedelta(days=20 - m_i * 2)
        mem_block = _make_block(conn, "memory", conv_act, ts=mem_ts)
        mem_id = uid("mem-")

        # Determine destination act
        dest_act = acts[0]["act_id"] if acts else "your-story"
        is_your_story = 1 if not acts else 0

        conn.execute(
            """INSERT INTO memories (id, block_id, conversation_id, narrative,
               destination_act_id, is_your_story, status, extraction_model,
               extraction_confidence, source, created_at)
               VALUES (?, ?, ?, ?, ?, ?, 'approved', 'test-gen', 0.85,
                       'compression', ?)""",
            (mem_id, mem_block, conv_id, mem["narrative"],
             dest_act, is_your_story, iso(mem_ts)),
        )

        # Create memory entity
        ent_type = mem.get("entity_type", "insight")
        ent_data = mem.get("entity_data", {"note": mem["narrative"]})
        conn.execute(
            """INSERT INTO memory_entities (id, memory_id, entity_type,
               entity_data, is_active, created_at)
               VALUES (?, ?, ?, ?, 1, ?)""",
            (uid("ent-"), mem_id, ent_type, json.dumps(ent_data), iso(mem_ts)),
        )

    conn.commit()


def generate_emails_data(conn, emails: list[dict]):
    """Insert mock emails into the database."""
    for email in emails:
        conn.execute(
            """INSERT INTO mock_emails (id, message_id, subject, sender,
               recipients, date, body, is_read, folder, has_attachment,
               importance)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (email["id"], email["message_id"], email["subject"],
             email["sender"], email["recipients"], email["date"],
             email["body"], email["is_read"], email["folder"],
             email["has_attachment"], email["importance"]),
        )
    conn.commit()


def generate_calendar_data(conn, events: list[dict], acts: list[dict]):
    """Insert mock calendar events and link some to scenes."""
    for event in events:
        conn.execute(
            """INSERT INTO mock_calendar_events (id, title, start_time,
               end_time, location, description, calendar_name, all_day,
               recurrence_rule, attendees)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (event["id"], event["title"], event["start_time"],
             event["end_time"], event["location"], event["description"],
             event["calendar_name"], event["all_day"],
             event["recurrence_rule"], event["attendees"]),
        )

    # Link some calendar events to scenes (project-related meetings)
    if acts:
        project_events = [e for e in events if any(
            a["title"] in e["title"] for a in acts
        )]
        for event in project_events[:5]:
            # Find a scene from the matching act
            for act in acts:
                if act["title"] in event["title"] and act["scene_ids"]:
                    scene_id = act["scene_ids"][0]
                    conn.execute(
                        """UPDATE scenes SET
                           calendar_event_id = ?,
                           calendar_event_start = ?,
                           calendar_event_end = ?,
                           calendar_event_title = ?
                           WHERE scene_id = ?""",
                        (event["id"], event["start_time"],
                         event["end_time"], event["title"], scene_id),
                    )
                    break

    conn.commit()


def generate_profile(profile: dict, output_dir: Path):
    """Generate complete database for a single profile."""
    profile_dir = output_dir / profile["id"]
    db_path = profile_dir / "talkingrock.db"

    conn = create_database(str(db_path))

    # System acts first (FK target for conversations)
    generate_system_acts(conn)

    # Your Story
    generate_your_story(conn, profile)

    # User acts + scenes
    acts = generate_acts(conn, profile)

    # Conversations
    generate_conversations(conn, profile, acts)

    # Memories
    generate_memories(conn, profile, acts)

    # Emails
    from .email_generator import generate_emails
    emails = generate_emails(profile)
    generate_emails_data(conn, emails)

    # Calendar
    from .calendar_generator import generate_calendar_events
    cal_events = generate_calendar_events(profile)
    generate_calendar_data(conn, cal_events, acts)

    conn.close()

    # Write profile metadata for harness consumption
    import json as _json
    meta_path = profile_dir / "profile.json"
    meta = {
        "id": profile["id"],
        "personality": profile.get("personality", "analytical"),
        "identity": profile.get("identity", {}),
    }
    meta_path.write_text(_json.dumps(meta, indent=2))

    # Report stats
    conn2 = sqlite3.connect(str(db_path))
    stats = {
        "acts": conn2.execute("SELECT COUNT(*) FROM acts").fetchone()[0],
        "scenes": conn2.execute("SELECT COUNT(*) FROM scenes").fetchone()[0],
        "conversations": conn2.execute("SELECT COUNT(*) FROM conversations").fetchone()[0],
        "messages": conn2.execute("SELECT COUNT(*) FROM messages").fetchone()[0],
        "memories": conn2.execute("SELECT COUNT(*) FROM memories").fetchone()[0],
        "emails": conn2.execute("SELECT COUNT(*) FROM mock_emails").fetchone()[0],
        "calendar": conn2.execute("SELECT COUNT(*) FROM mock_calendar_events").fetchone()[0],
        "blocks": conn2.execute("SELECT COUNT(*) FROM blocks").fetchone()[0],
        "pages": conn2.execute("SELECT COUNT(*) FROM pages").fetchone()[0],
    }
    conn2.close()

    return stats
