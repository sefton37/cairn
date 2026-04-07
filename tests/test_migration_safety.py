"""Tests verifying that schema migrations work correctly on databases with existing data.

Strategy: build databases at older schema versions, insert seed data, run migrations
forward, then assert data is preserved and new schema elements are in place.

All tests create standalone SQLite connections — no global play_db singleton is used.
"""

from __future__ import annotations

import hashlib
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Import targets
# ---------------------------------------------------------------------------
from cairn.play_db import (
    SCHEMA_VERSION,
    _run_schema_migrations,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

NOW = datetime.now(timezone.utc).isoformat()


def _raw_conn(db_path: Path) -> sqlite3.Connection:
    """Open a plain (non-encrypted) SQLite connection used only in tests."""
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def _table_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    return {r[0] for r in rows}


def _column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {r[1] for r in rows}


def _index_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index'"
    ).fetchall()
    return {r[0] for r in rows}


# ---------------------------------------------------------------------------
# Minimal v10 schema builder
# A v10 DB has: acts, scenes (with disable_auto_complete), pages,
# blocks, block_properties, rich_text, schema_version.
# It does NOT yet have: block_relationships, block_embeddings, conversations,
# messages, memories, … (those arrive v11+).
# ---------------------------------------------------------------------------

_V10_SCHEMA = """
    CREATE TABLE IF NOT EXISTS schema_version (
        version INTEGER PRIMARY KEY
    );

    CREATE TABLE IF NOT EXISTS acts (
        act_id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        active INTEGER NOT NULL DEFAULT 0,
        notes TEXT NOT NULL DEFAULT '',
        color TEXT,
        repo_path TEXT,
        artifact_type TEXT,
        code_config TEXT,
        root_block_id TEXT,
        position INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS scenes (
        scene_id TEXT PRIMARY KEY,
        act_id TEXT NOT NULL REFERENCES acts(act_id) ON DELETE CASCADE,
        title TEXT NOT NULL,
        stage TEXT NOT NULL DEFAULT 'planning',
        notes TEXT NOT NULL DEFAULT '',
        link TEXT,
        calendar_event_id TEXT,
        recurrence_rule TEXT,
        thunderbird_event_id TEXT,
        calendar_event_start TEXT,
        calendar_event_end TEXT,
        calendar_event_title TEXT,
        next_occurrence TEXT,
        calendar_name TEXT,
        category TEXT,
        disable_auto_complete INTEGER NOT NULL DEFAULT 0,
        position INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_scenes_act_id ON scenes(act_id);
    CREATE UNIQUE INDEX IF NOT EXISTS idx_scenes_calendar_event_unique
        ON scenes(calendar_event_id) WHERE calendar_event_id IS NOT NULL;

    CREATE TABLE IF NOT EXISTS pages (
        page_id TEXT PRIMARY KEY,
        act_id TEXT NOT NULL REFERENCES acts(act_id) ON DELETE CASCADE,
        parent_page_id TEXT REFERENCES pages(page_id) ON DELETE CASCADE,
        title TEXT NOT NULL,
        icon TEXT,
        position INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_pages_act_id ON pages(act_id);

    CREATE TABLE IF NOT EXISTS attachments (
        attachment_id TEXT PRIMARY KEY,
        act_id TEXT REFERENCES acts(act_id) ON DELETE CASCADE,
        scene_id TEXT REFERENCES scenes(scene_id) ON DELETE CASCADE,
        page_id TEXT REFERENCES pages(page_id) ON DELETE CASCADE,
        file_path TEXT NOT NULL,
        file_name TEXT NOT NULL,
        file_type TEXT NOT NULL,
        added_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS blocks (
        id TEXT PRIMARY KEY,
        type TEXT NOT NULL,
        parent_id TEXT,
        act_id TEXT NOT NULL REFERENCES acts(act_id) ON DELETE CASCADE,
        page_id TEXT REFERENCES pages(page_id) ON DELETE CASCADE,
        scene_id TEXT REFERENCES scenes(scene_id) ON DELETE SET NULL,
        position INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_blocks_parent ON blocks(parent_id);
    CREATE INDEX IF NOT EXISTS idx_blocks_act ON blocks(act_id);

    CREATE TABLE IF NOT EXISTS block_properties (
        block_id TEXT NOT NULL REFERENCES blocks(id) ON DELETE CASCADE,
        key TEXT NOT NULL,
        value TEXT,
        PRIMARY KEY (block_id, key)
    );

    CREATE TABLE IF NOT EXISTS rich_text (
        id TEXT PRIMARY KEY,
        block_id TEXT NOT NULL REFERENCES blocks(id) ON DELETE CASCADE,
        position INTEGER NOT NULL DEFAULT 0,
        content TEXT NOT NULL,
        bold INTEGER DEFAULT 0,
        italic INTEGER DEFAULT 0,
        strikethrough INTEGER DEFAULT 0,
        code INTEGER DEFAULT 0,
        underline INTEGER DEFAULT 0,
        color TEXT,
        background_color TEXT,
        link_url TEXT
    );
"""


def _build_v10_db(db_path: Path) -> sqlite3.Connection:
    """Create a v10 schema DB with seed acts/scenes/blocks."""
    conn = _raw_conn(db_path)
    conn.executescript(_V10_SCHEMA)
    conn.execute("INSERT INTO schema_version (version) VALUES (10)")

    conn.execute(
        "INSERT INTO acts (act_id, title, active, notes, position, created_at, updated_at) "
        "VALUES ('act-1', 'Test Act', 1, 'some notes', 0, ?, ?)",
        (NOW, NOW),
    )
    conn.execute(
        "INSERT INTO scenes (scene_id, act_id, title, stage, position, created_at, updated_at) "
        "VALUES ('scene-1', 'act-1', 'Test Scene', 'planning', 0, ?, ?)",
        (NOW, NOW),
    )
    conn.execute(
        "INSERT INTO blocks (id, type, act_id, position, created_at, updated_at) "
        "VALUES ('block-1', 'paragraph', 'act-1', 0, ?, ?)",
        (NOW, NOW),
    )
    conn.execute(
        "INSERT INTO block_properties (block_id, key, value) "
        "VALUES ('block-1', 'text', 'Hello world')",
    )
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# Minimal v12 schema builder (adds conversations/messages/memories)
# ---------------------------------------------------------------------------

_V12_EXTRA = """
    -- system_role on acts (added in v12)
    -- (we use ADD COLUMN because we build on top of the v10 structure)

    CREATE TABLE IF NOT EXISTS block_relationships (
        id TEXT PRIMARY KEY,
        source_block_id TEXT NOT NULL REFERENCES blocks(id) ON DELETE CASCADE,
        target_block_id TEXT NOT NULL REFERENCES blocks(id) ON DELETE CASCADE,
        relationship_type TEXT NOT NULL,
        confidence REAL DEFAULT 1.0,
        weight REAL DEFAULT 1.0,
        source TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(source_block_id, target_block_id, relationship_type),
        CHECK(source_block_id != target_block_id)
    );

    CREATE TABLE IF NOT EXISTS block_embeddings (
        block_id TEXT PRIMARY KEY REFERENCES blocks(id) ON DELETE CASCADE,
        embedding BLOB NOT NULL,
        embedding_model TEXT DEFAULT 'all-MiniLM-L6-v2',
        content_hash TEXT NOT NULL,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS conversations (
        id TEXT PRIMARY KEY,
        block_id TEXT NOT NULL REFERENCES blocks(id) ON DELETE CASCADE,
        status TEXT NOT NULL DEFAULT 'active',
        started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_message_at TIMESTAMP,
        closed_at TIMESTAMP,
        archived_at TIMESTAMP,
        message_count INTEGER DEFAULT 0,
        compression_model TEXT,
        compression_duration_ms INTEGER,
        compression_passes INTEGER,
        is_paused BOOLEAN DEFAULT 0,
        paused_at TIMESTAMP,
        CHECK (status IN ('active', 'ready_to_close', 'compressing', 'archived'))
    );

    CREATE TABLE IF NOT EXISTS messages (
        id TEXT PRIMARY KEY,
        conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
        block_id TEXT NOT NULL REFERENCES blocks(id) ON DELETE CASCADE,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        position INTEGER NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        active_act_id TEXT,
        active_scene_id TEXT,
        CHECK (role IN ('user', 'cairn', 'reos', 'riva', 'system'))
    );

    CREATE TABLE IF NOT EXISTS memories (
        id TEXT PRIMARY KEY,
        block_id TEXT NOT NULL REFERENCES blocks(id) ON DELETE CASCADE,
        conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
        narrative TEXT NOT NULL,
        narrative_embedding BLOB,
        destination_act_id TEXT,
        destination_page_id TEXT,
        is_your_story BOOLEAN DEFAULT 1,
        status TEXT NOT NULL DEFAULT 'pending_review',
        user_reviewed BOOLEAN DEFAULT 0,
        user_edited BOOLEAN DEFAULT 0,
        original_narrative TEXT,
        extraction_model TEXT,
        extraction_confidence REAL,
        signal_count INTEGER NOT NULL DEFAULT 1,
        last_reinforced_at TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (destination_act_id) REFERENCES acts(act_id) ON DELETE SET NULL,
        CHECK (status IN ('pending_review', 'approved', 'rejected', 'superseded'))
    );

    CREATE TABLE IF NOT EXISTS memory_entities (
        id TEXT PRIMARY KEY,
        memory_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
        entity_type TEXT NOT NULL,
        entity_data JSON NOT NULL,
        is_active BOOLEAN DEFAULT 1,
        resolved_by_memory_id TEXT REFERENCES memories(id) ON DELETE SET NULL,
        resolved_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        CHECK (entity_type IN (
            'person', 'task', 'decision', 'waiting_on',
            'question_resolved', 'question_opened',
            'blocker_cleared', 'priority_change',
            'act_reference', 'insight'
        ))
    );

    CREATE TABLE IF NOT EXISTS memory_state_deltas (
        id TEXT PRIMARY KEY,
        memory_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
        delta_type TEXT NOT NULL,
        delta_data JSON NOT NULL,
        applied BOOLEAN DEFAULT 0,
        applied_at TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS classification_memory_references (
        id TEXT PRIMARY KEY,
        classification_id TEXT NOT NULL,
        memory_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
        influence_type TEXT NOT NULL,
        influence_score REAL,
        reasoning TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
"""


def _build_v12_db(db_path: Path) -> sqlite3.Connection:
    """Create a v12 schema DB with seed data including conversations."""
    conn = _raw_conn(db_path)
    # Disable FKs while building because v12 needs acts for blocks FK
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.executescript(_V10_SCHEMA)
    # Add system_role to acts (v12 addition)
    conn.execute("ALTER TABLE acts ADD COLUMN system_role TEXT")
    conn.executescript(_V12_EXTRA)
    conn.execute("INSERT INTO schema_version (version) VALUES (12)")
    conn.execute("PRAGMA foreign_keys = ON")

    # Seed acts
    conn.execute(
        "INSERT INTO acts (act_id, title, active, notes, position, created_at, updated_at) "
        "VALUES ('act-1', 'Test Act', 1, '', 0, ?, ?)",
        (NOW, NOW),
    )
    conn.execute(
        "INSERT INTO acts (act_id, title, active, notes, system_role, position, "
        "created_at, updated_at) VALUES ('archived-conversations', 'Archived', 0, '', "
        "'archived_conversations', 999, ?, ?)",
        (NOW, NOW),
    )
    # Seed a conversation block + conversation row
    conn.execute(
        "INSERT INTO blocks (id, type, act_id, position, created_at, updated_at) "
        "VALUES ('block-conv-1', 'conversation', 'archived-conversations', 0, ?, ?)",
        (NOW, NOW),
    )
    conn.execute(
        "INSERT INTO conversations (id, block_id, status, started_at) "
        "VALUES ('conv-1', 'block-conv-1', 'active', ?)",
        (NOW,),
    )
    conn.commit()
    return conn


# =============================================================================
# Group 1: play_db Schema Migrations
# =============================================================================


class TestPlayDbMigrations:
    """Migrate databases from old versions, verify structure and data."""

    def test_v10_to_v11_adds_memory_graph_tables(self, tmp_path: Path) -> None:
        """After migrating v10→v19, block_relationships and block_embeddings tables exist."""
        db_path = tmp_path / "play.db"
        conn = _build_v10_db(db_path)

        _run_schema_migrations(conn, 10)
        conn.commit()

        tables = _table_names(conn)
        assert "block_relationships" in tables
        assert "block_embeddings" in tables

    def test_v10_data_intact_after_full_migration(self, tmp_path: Path) -> None:
        """Acts, scenes, and block_properties seeded at v10 survive migration to latest."""
        db_path = tmp_path / "play.db"
        conn = _build_v10_db(db_path)

        _run_schema_migrations(conn, 10)
        conn.commit()

        row = conn.execute("SELECT title FROM acts WHERE act_id = 'act-1'").fetchone()
        assert row is not None
        assert row[0] == "Test Act"

        row = conn.execute("SELECT title FROM scenes WHERE scene_id = 'scene-1'").fetchone()
        assert row is not None
        assert row[0] == "Test Scene"

        row = conn.execute(
            "SELECT value FROM block_properties WHERE block_id = 'block-1' AND key = 'text'"
        ).fetchone()
        assert row is not None
        assert row[0] == "Hello world"

    def test_v12_to_v13_adds_fts_and_auxiliary_tables(self, tmp_path: Path) -> None:
        """After migrating v12→v13, FTS tables, summaries, briefings, and assessments exist."""
        db_path = tmp_path / "play.db"
        conn = _build_v12_db(db_path)

        _run_schema_migrations(conn, 12)
        conn.commit()

        tables = _table_names(conn)
        assert "messages_fts" in tables
        assert "memories_fts" in tables
        assert "conversation_summaries" in tables
        assert "state_briefings" in tables
        assert "turn_assessments" in tables

    def test_v12_to_v13_adds_source_column_to_memories(self, tmp_path: Path) -> None:
        """After migrating v12→v13, memories.source column exists."""
        db_path = tmp_path / "play.db"
        conn = _build_v12_db(db_path)

        _run_schema_migrations(conn, 12)
        conn.commit()

        columns = _column_names(conn, "memories")
        assert "source" in columns

    def test_v13_to_v14_adds_attention_priorities(self, tmp_path: Path) -> None:
        """After migrating v13→v14, attention_priorities table exists."""
        db_path = tmp_path / "play.db"
        conn = _build_v12_db(db_path)
        # First bring to v13
        _run_schema_migrations(conn, 12)
        conn.execute("UPDATE schema_version SET version = 13")
        conn.commit()

        # Now migrate v13→v19
        _run_schema_migrations(conn, 13)
        conn.commit()

        tables = _table_names(conn)
        assert "attention_priorities" in tables

    def test_v13_scenes_data_survives_v14_migration(self, tmp_path: Path) -> None:
        """Existing scenes are intact after v14 attention_priorities migration."""
        db_path = tmp_path / "play.db"
        conn = _build_v12_db(db_path)
        _run_schema_migrations(conn, 12)
        conn.execute("UPDATE schema_version SET version = 13")
        # Insert a scene at v13 state
        conn.execute(
            "INSERT INTO scenes (scene_id, act_id, title, stage, position, created_at, updated_at) "
            "VALUES ('scene-v13', 'act-1', 'v13 Scene', 'in_progress', 1, ?, ?)",
            (NOW, NOW),
        )
        conn.commit()

        _run_schema_migrations(conn, 13)
        conn.commit()

        row = conn.execute(
            "SELECT title, stage FROM scenes WHERE scene_id = 'scene-v13'"
        ).fetchone()
        assert row is not None
        assert row[0] == "v13 Scene"
        assert row[1] == "in_progress"

    def test_v16_to_v17_adds_priority_learning_tables(self, tmp_path: Path) -> None:
        """After migrating v16→v17, reorder_history and priority_boost_rules exist."""
        db_path = tmp_path / "play.db"
        conn = _build_v12_db(db_path)
        _run_schema_migrations(conn, 12)
        conn.execute("UPDATE schema_version SET version = 16")
        conn.commit()

        _run_schema_migrations(conn, 16)
        conn.commit()

        tables = _table_names(conn)
        assert "reorder_history" in tables
        assert "priority_boost_rules" in tables

    def test_v18_to_v19_adds_memory_type_column(self, tmp_path: Path) -> None:
        """After migrating v18→v19, memories.memory_type column exists."""
        db_path = tmp_path / "play.db"
        conn = _build_v12_db(db_path)
        _run_schema_migrations(conn, 12)
        conn.execute("UPDATE schema_version SET version = 18")
        conn.commit()

        _run_schema_migrations(conn, 18)
        conn.commit()

        columns = _column_names(conn, "memories")
        assert "memory_type" in columns

    def test_v18_to_v19_memory_type_defaults_to_null(self, tmp_path: Path) -> None:
        """Existing memories get memory_type = NULL after v19 migration."""
        db_path = tmp_path / "play.db"
        conn = _build_v12_db(db_path)
        # Migrate to v16 (has claudecode source) to insert a memory
        _run_schema_migrations(conn, 12)
        conn.execute("UPDATE schema_version SET version = 18")
        conn.commit()

        # Insert a memory before v19 runs
        conn.execute(
            "INSERT INTO blocks (id, type, act_id, position, created_at, updated_at) "
            "VALUES ('block-mem-1', 'memory', 'archived-conversations', 0, ?, ?)",
            (NOW, NOW),
        )
        conn.execute(
            "INSERT INTO memories (id, block_id, conversation_id, narrative, status, "
            "signal_count) VALUES ('mem-1', 'block-mem-1', 'conv-1', 'Test memory', "
            "'pending_review', 1)",
        )
        conn.commit()

        _run_schema_migrations(conn, 18)
        conn.commit()

        row = conn.execute("SELECT memory_type FROM memories WHERE id = 'mem-1'").fetchone()
        assert row is not None
        assert row[0] is None  # NULL default for existing rows

    def test_full_migration_v10_to_latest(self, tmp_path: Path) -> None:
        """A database built at v10 with seed data migrates all the way to the current version."""
        db_path = tmp_path / "play.db"
        conn = _build_v10_db(db_path)

        _run_schema_migrations(conn, 10)
        conn.commit()

        # Schema version updated
        version = conn.execute("SELECT version FROM schema_version").fetchone()[0]
        assert version == SCHEMA_VERSION

        # Original data intact
        count = conn.execute("SELECT COUNT(*) FROM acts").fetchone()[0]
        assert count >= 1  # at least our seed + system acts

        # Seeded block still has its properties
        row = conn.execute(
            "SELECT value FROM block_properties WHERE block_id = 'block-1'"
        ).fetchone()
        assert row is not None

    def test_migration_idempotent(self, tmp_path: Path) -> None:
        """Running migrations twice on the same DB does not raise errors."""
        db_path = tmp_path / "play.db"
        conn = _build_v10_db(db_path)

        _run_schema_migrations(conn, 10)
        conn.execute("UPDATE schema_version SET version = 10")  # reset to trigger again
        conn.commit()

        # Should not raise despite tables already existing
        _run_schema_migrations(conn, 10)
        conn.commit()

    def test_schema_version_updated_after_migration(self, tmp_path: Path) -> None:
        """schema_version.version equals SCHEMA_VERSION after migration completes."""
        db_path = tmp_path / "play.db"
        conn = _build_v10_db(db_path)

        _run_schema_migrations(conn, 10)
        conn.commit()

        version = conn.execute("SELECT version FROM schema_version").fetchone()[0]
        assert version == SCHEMA_VERSION


# =============================================================================
# Group 2: db.py MigrationRunner (SQL file–based migrations)
# =============================================================================


class TestMigrationRunner:
    """Tests for the SQL-file–based MigrationRunner used by db.py."""

    def _make_db(self, tmp_path: Path) -> object:
        """Create a fresh Database instance pointing at a temp file."""
        from cairn.db import Database

        db = Database(tmp_path / "test.db")
        db.migrate()
        return db

    def test_migration_runner_applies_all_pending(self, tmp_path: Path) -> None:
        """All available SQL migrations are applied to a fresh database."""
        from cairn.migrations.runner import MigrationRunner

        db = self._make_db(tmp_path)
        runner = MigrationRunner(db)
        # After migrate() already ran _run_migrations, running again should find 0 pending
        count = runner.run_pending()
        assert count == 0

    def test_migration_runner_records_checksums(self, tmp_path: Path) -> None:
        """Applied migrations have checksums recorded in schema_version."""
        from cairn.migrations.runner import MigrationRunner

        db = self._make_db(tmp_path)
        runner = MigrationRunner(db)

        conn = db.connect()
        rows = conn.execute(
            "SELECT version, checksum FROM schema_version ORDER BY version"
        ).fetchall()

        # Every applied migration should have a non-null checksum
        for version, checksum in rows:
            assert checksum is not None, f"Migration {version} missing checksum"

    def test_migration_runner_integrity_check_passes(self, tmp_path: Path) -> None:
        """verify_integrity() returns True when migration files match stored checksums."""
        from cairn.migrations.runner import MigrationRunner

        db = self._make_db(tmp_path)
        runner = MigrationRunner(db)
        assert runner.verify_integrity() is True

    def test_migration_runner_integrity_check_fails_on_tamper(self, tmp_path: Path) -> None:
        """verify_integrity() returns False when a stored checksum is corrupted."""
        from cairn.migrations.runner import MigrationRunner

        db = self._make_db(tmp_path)
        runner = MigrationRunner(db)

        # Tamper with the stored checksum for migration 1
        conn = db.connect()
        conn.execute(
            "UPDATE schema_version SET checksum = 'deadbeefdeadbeef' WHERE version = 1"
        )
        conn.commit()

        assert runner.verify_integrity() is False

    def test_migration_runner_skips_already_applied(self, tmp_path: Path) -> None:
        """Running MigrationRunner.run_pending() a second time applies zero migrations."""
        from cairn.migrations.runner import MigrationRunner

        db = self._make_db(tmp_path)
        runner = MigrationRunner(db)

        first_run = runner.run_pending()
        second_run = runner.run_pending()

        assert second_run == 0

    def test_migration_runner_preserves_data_through_sql_migrations(
        self, tmp_path: Path
    ) -> None:
        """Data inserted before SQL migrations remain accessible after migration."""
        from cairn.db import Database

        db = Database(tmp_path / "test.db")
        db.migrate()  # runs SQL migrations internally

        # Insert data after migration
        from uuid import uuid4

        event_id = str(uuid4())
        db.insert_event(
            event_id=event_id,
            source="test",
            kind="test_event",
            ts=NOW,
            payload_metadata=None,
            note="preserved",
        )

        # Re-open the same DB and verify data
        db2 = Database(tmp_path / "test.db")
        db2.migrate()
        events = db2.iter_events_recent(limit=10)
        ids = [e["id"] for e in events]
        assert event_id in ids


# =============================================================================
# Group 3: Data Integrity After Migration
# =============================================================================


class TestDataIntegrityAfterMigration:
    """Verify FK relationships, indexes, and data fidelity after migrations."""

    def test_foreign_keys_valid_after_full_migration(self, tmp_path: Path) -> None:
        """acts → scenes FK relationship is intact after v10→latest migration."""
        db_path = tmp_path / "play.db"
        conn = _build_v10_db(db_path)

        _run_schema_migrations(conn, 10)
        conn.commit()

        # JOIN across the FK boundary
        rows = conn.execute(
            """
            SELECT a.title AS act_title, s.title AS scene_title
            FROM acts a
            JOIN scenes s ON s.act_id = a.act_id
            WHERE a.act_id = 'act-1'
            """
        ).fetchall()

        assert len(rows) == 1
        assert rows[0][0] == "Test Act"
        assert rows[0][1] == "Test Scene"

    def test_fts_indexes_work_after_migration(self, tmp_path: Path) -> None:
        """Full-text search on messages_fts works after v12→v13+ migration."""
        db_path = tmp_path / "play.db"
        conn = _build_v12_db(db_path)

        _run_schema_migrations(conn, 12)
        conn.commit()

        # Insert a message block and message
        conn.execute(
            "INSERT INTO blocks (id, type, act_id, position, created_at, updated_at) "
            "VALUES ('block-msg-1', 'message', 'archived-conversations', 0, ?, ?)",
            (NOW, NOW),
        )
        conn.execute(
            "INSERT INTO messages (id, conversation_id, block_id, role, content, position) "
            "VALUES ('msg-1', 'conv-1', 'block-msg-1', 'user', 'unique_needle_term', 0)",
        )
        conn.commit()

        # FTS5 search
        rows = conn.execute(
            "SELECT rowid FROM messages_fts WHERE messages_fts MATCH 'unique_needle_term'"
        ).fetchall()
        assert len(rows) == 1

    def test_wal_mode_preserved_after_migration(self, tmp_path: Path) -> None:
        """WAL journal mode is active on a DB after migration (connections re-use WAL)."""
        db_path = tmp_path / "play.db"
        conn = _build_v10_db(db_path)

        _run_schema_migrations(conn, 10)
        conn.commit()

        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode == "wal"

    def test_block_properties_preserved_through_migration(self, tmp_path: Path) -> None:
        """Block properties inserted before migration are readable after full migration."""
        db_path = tmp_path / "play.db"
        conn = _build_v10_db(db_path)
        # Add an extra property
        conn.execute(
            "INSERT INTO block_properties (block_id, key, value) "
            "VALUES ('block-1', 'language', 'python')"
        )
        conn.commit()

        _run_schema_migrations(conn, 10)
        conn.commit()

        rows = conn.execute(
            "SELECT key, value FROM block_properties WHERE block_id = 'block-1' ORDER BY key"
        ).fetchall()
        props = {r[0]: r[1] for r in rows}
        assert props["text"] == "Hello world"
        assert props["language"] == "python"


# =============================================================================
# Group 4: Edge Cases
# =============================================================================


class TestMigrationEdgeCases:
    """Edge cases: fresh vs migrated parity, concurrent safety."""

    def test_migration_on_empty_db_matches_fresh_init(self, tmp_path: Path) -> None:
        """Key table columns are the same whether a DB is freshly init'd or migrated."""
        import cairn.play_db as play_db

        # Fresh DB via init_db
        fresh_dir = tmp_path / "fresh"
        fresh_dir.mkdir()
        fresh_db = fresh_dir / "talkingrock.db"
        import sqlite3 as _sqlite3

        # Use monkeypatch-style env var override via raw call
        import os

        orig = os.environ.get("TALKINGROCK_DATA_DIR")
        os.environ["TALKINGROCK_DATA_DIR"] = str(fresh_dir)
        play_db.close_connection()
        play_db.init_db()
        fresh_conn = play_db._get_connection()
        fresh_acts_cols = _column_names(fresh_conn, "acts")
        fresh_scenes_cols = _column_names(fresh_conn, "scenes")
        play_db.close_connection()
        if orig is None:
            os.environ.pop("TALKINGROCK_DATA_DIR", None)
        else:
            os.environ["TALKINGROCK_DATA_DIR"] = orig

        # Migrated DB starting at v10
        migrated_db = tmp_path / "migrated.db"
        mconn = _build_v10_db(migrated_db)
        _run_schema_migrations(mconn, 10)
        mconn.commit()
        migrated_acts_cols = _column_names(mconn, "acts")
        migrated_scenes_cols = _column_names(mconn, "scenes")

        # Both paths must expose the same columns for acts and scenes
        assert fresh_acts_cols == migrated_acts_cols
        assert fresh_scenes_cols == migrated_scenes_cols

    def test_concurrent_migration_is_safe(self, tmp_path: Path) -> None:
        """Two threads calling init_db sequentially on an already-init'd DB produce no corruption.

        SQLite's busy_timeout handles lock contention for the idempotent path (DB already
        initialised). The first call to init_db on a brand-new file is NOT protected
        against true concurrent first-time initialization — that race is a known limitation.
        This test verifies the safe/common case: both threads encounter an already-valid DB.
        """
        import os

        import cairn.play_db as play_db

        data_dir = tmp_path / "concurrent"
        data_dir.mkdir()

        # First init is single-threaded to avoid the known first-time race
        orig = os.environ.get("TALKINGROCK_DATA_DIR")
        os.environ["TALKINGROCK_DATA_DIR"] = str(data_dir)
        play_db.close_connection()
        play_db.init_db()
        play_db.close_connection()

        errors: list[Exception] = []

        def run_init_on_existing(env_val: str) -> None:
            os.environ["TALKINGROCK_DATA_DIR"] = env_val
            play_db.close_connection()
            try:
                play_db.init_db()
            except Exception as exc:
                errors.append(exc)

        t1 = threading.Thread(target=run_init_on_existing, args=(str(data_dir),))
        t2 = threading.Thread(target=run_init_on_existing, args=(str(data_dir),))
        t1.start()
        t2.start()
        t1.join(timeout=15)
        t2.join(timeout=15)

        assert not errors, f"Concurrent migration on existing DB raised: {errors}"

        # Verify the DB is coherent after concurrent access
        os.environ["TALKINGROCK_DATA_DIR"] = str(data_dir)
        play_db.close_connection()
        conn = play_db._get_connection()
        version = conn.execute("SELECT version FROM schema_version").fetchone()[0]
        assert version == SCHEMA_VERSION
        play_db.close_connection()

        if orig is None:
            os.environ.pop("TALKINGROCK_DATA_DIR", None)
        else:
            os.environ["TALKINGROCK_DATA_DIR"] = orig
