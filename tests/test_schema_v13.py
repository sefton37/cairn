"""Tests for v13 schema migration.

Verifies:
- Fresh install creates all v13 tables and columns
- source column on memories with CHECK constraint
- FTS5 virtual tables for messages and memories
- FTS5 triggers sync on INSERT/UPDATE/DELETE
- conversation_summaries, state_briefings, turn_assessments tables
"""

from __future__ import annotations

import sqlite3
import uuid

import pytest

from cairn.play_db import (
    SCHEMA_VERSION,
    _get_connection,
    close_connection,
    init_db,
)


@pytest.fixture(autouse=True)
def _fresh_db(tmp_path, monkeypatch):
    """Use a fresh temporary database for each test."""
    monkeypatch.setenv("REOS_DATA_DIR", str(tmp_path))
    close_connection()
    init_db()
    yield
    close_connection()


def _get_tables(conn: sqlite3.Connection) -> set[str]:
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
    )
    return {row[0] for row in cursor.fetchall()}


def _get_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    cursor = conn.execute(f"PRAGMA table_info({table})")
    return [row[1] for row in cursor.fetchall()]


def _get_triggers(conn: sqlite3.Connection) -> set[str]:
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type = 'trigger'")
    return {row[0] for row in cursor.fetchall()}


class TestSchemaV13Fresh:
    """Tests for fresh v13 schema install."""

    def test_schema_version_is_current(self):
        assert SCHEMA_VERSION == 14
        conn = _get_connection()
        cursor = conn.execute("SELECT version FROM schema_version LIMIT 1")
        row = cursor.fetchone()
        assert row[0] == 14

    def test_memories_has_source_column(self):
        conn = _get_connection()
        columns = _get_columns(conn, "memories")
        assert "source" in columns

    def test_source_default_is_compression(self):
        """Memories created without explicit source default to 'compression'."""
        conn = _get_connection()
        # We need a block and conversation to create a memory
        now = "2026-01-01T00:00:00+00:00"
        act_id = "your-story"
        block_id = f"block-{uuid.uuid4().hex[:12]}"
        conv_block_id = f"block-{uuid.uuid4().hex[:12]}"
        conv_id = uuid.uuid4().hex[:12]

        conn.execute(
            "INSERT INTO blocks (id, type, act_id, position, created_at, updated_at) "
            "VALUES (?, 'conversation', ?, 0, ?, ?)",
            (conv_block_id, act_id, now, now),
        )
        conn.execute(
            "INSERT INTO conversations (id, block_id, status, started_at) "
            "VALUES (?, ?, 'active', ?)",
            (conv_id, conv_block_id, now),
        )
        conn.execute(
            "INSERT INTO blocks (id, type, act_id, position, created_at, updated_at) "
            "VALUES (?, 'memory', ?, 0, ?, ?)",
            (block_id, act_id, now, now),
        )
        conn.execute(
            "INSERT INTO memories (id, block_id, conversation_id, narrative, "
            "status, signal_count, created_at) "
            "VALUES (?, ?, ?, 'test narrative', 'pending_review', 1, ?)",
            ("mem-1", block_id, conv_id, now),
        )
        conn.commit()

        cursor = conn.execute("SELECT source FROM memories WHERE id = 'mem-1'")
        row = cursor.fetchone()
        assert row[0] == "compression"

    def test_source_check_constraint_valid(self):
        """Only 'compression' and 'turn_assessment' are valid source values."""
        conn = _get_connection()
        now = "2026-01-01T00:00:00+00:00"
        act_id = "your-story"
        block_id = f"block-{uuid.uuid4().hex[:12]}"
        conv_block_id = f"block-{uuid.uuid4().hex[:12]}"
        conv_id = uuid.uuid4().hex[:12]

        conn.execute(
            "INSERT INTO blocks (id, type, act_id, position, created_at, updated_at) "
            "VALUES (?, 'conversation', ?, 0, ?, ?)",
            (conv_block_id, act_id, now, now),
        )
        conn.execute(
            "INSERT INTO conversations (id, block_id, status, started_at) "
            "VALUES (?, ?, 'active', ?)",
            (conv_id, conv_block_id, now),
        )
        conn.execute(
            "INSERT INTO blocks (id, type, act_id, position, created_at, updated_at) "
            "VALUES (?, 'memory', ?, 0, ?, ?)",
            (block_id, act_id, now, now),
        )
        conn.commit()

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO memories (id, block_id, conversation_id, narrative, "
                "status, signal_count, source, created_at) "
                "VALUES (?, ?, ?, 'test', 'pending_review', 1, 'invalid_source', ?)",
                ("mem-bad", block_id, conv_id, now),
            )

    def test_messages_fts_exists(self):
        tables = _get_tables(_get_connection())
        assert "messages_fts" in tables

    def test_memories_fts_exists(self):
        tables = _get_tables(_get_connection())
        assert "memories_fts" in tables

    def test_conversation_summaries_table_exists(self):
        tables = _get_tables(_get_connection())
        assert "conversation_summaries" in tables

    def test_state_briefings_table_exists(self):
        tables = _get_tables(_get_connection())
        assert "state_briefings" in tables

    def test_turn_assessments_table_exists(self):
        tables = _get_tables(_get_connection())
        assert "turn_assessments" in tables


class TestFTSTriggers:
    """Test that FTS5 triggers sync data correctly."""

    def _setup_conversation(self, conn):
        """Create prerequisite records for a message."""
        now = "2026-01-01T00:00:00+00:00"
        act_id = "your-story"
        conv_block_id = f"block-{uuid.uuid4().hex[:12]}"
        msg_block_id = f"block-{uuid.uuid4().hex[:12]}"
        conv_id = uuid.uuid4().hex[:12]

        conn.execute(
            "INSERT INTO blocks (id, type, act_id, position, created_at, updated_at) "
            "VALUES (?, 'conversation', ?, 0, ?, ?)",
            (conv_block_id, act_id, now, now),
        )
        conn.execute(
            "INSERT INTO conversations (id, block_id, status, started_at) "
            "VALUES (?, ?, 'active', ?)",
            (conv_id, conv_block_id, now),
        )
        conn.execute(
            "INSERT INTO blocks (id, type, act_id, position, created_at, updated_at) "
            "VALUES (?, 'message', ?, 0, ?, ?)",
            (msg_block_id, act_id, now, now),
        )
        conn.commit()
        return conv_id, msg_block_id, now

    def test_messages_fts_insert_trigger(self):
        conn = _get_connection()
        conv_id, msg_block_id, now = self._setup_conversation(conn)

        conn.execute(
            "INSERT INTO messages (id, conversation_id, block_id, role, content, position, created_at) "
            "VALUES (?, ?, ?, 'user', 'hello world fts test', 0, ?)",
            ("msg-1", conv_id, msg_block_id, now),
        )
        conn.commit()

        cursor = conn.execute(
            "SELECT * FROM messages_fts WHERE messages_fts MATCH 'hello'"
        )
        results = cursor.fetchall()
        assert len(results) == 1

    def test_messages_fts_delete_trigger(self):
        conn = _get_connection()
        conv_id, msg_block_id, now = self._setup_conversation(conn)

        conn.execute(
            "INSERT INTO messages (id, conversation_id, block_id, role, content, position, created_at) "
            "VALUES (?, ?, ?, 'user', 'deletable content test', 0, ?)",
            ("msg-del", conv_id, msg_block_id, now),
        )
        conn.commit()

        conn.execute("DELETE FROM messages WHERE id = 'msg-del'")
        conn.commit()

        cursor = conn.execute(
            "SELECT * FROM messages_fts WHERE messages_fts MATCH 'deletable'"
        )
        results = cursor.fetchall()
        assert len(results) == 0

    def test_fts_triggers_exist(self):
        triggers = _get_triggers(_get_connection())
        expected = {
            "messages_fts_insert", "messages_fts_delete", "messages_fts_update",
            "memories_fts_insert", "memories_fts_delete", "memories_fts_update",
        }
        assert expected.issubset(triggers)


class TestConversationSummariesTable:
    """Test conversation_summaries table structure."""

    def test_columns_exist(self):
        conn = _get_connection()
        columns = _get_columns(conn, "conversation_summaries")
        expected = {"id", "conversation_id", "summary", "summary_model",
                    "created_at", "updated_at"}
        assert expected == set(columns)

    def test_unique_conversation_id(self):
        """Only one summary per conversation."""
        conn = _get_connection()
        now = "2026-01-01T00:00:00+00:00"
        act_id = "your-story"
        conv_block_id = f"block-{uuid.uuid4().hex[:12]}"
        conv_id = uuid.uuid4().hex[:12]

        conn.execute(
            "INSERT INTO blocks (id, type, act_id, position, created_at, updated_at) "
            "VALUES (?, 'conversation', ?, 0, ?, ?)",
            (conv_block_id, act_id, now, now),
        )
        conn.execute(
            "INSERT INTO conversations (id, block_id, status, started_at) "
            "VALUES (?, ?, 'active', ?)",
            (conv_id, conv_block_id, now),
        )
        conn.execute(
            "INSERT INTO conversation_summaries (id, conversation_id, summary, created_at, updated_at) "
            "VALUES (?, ?, 'summary one', ?, ?)",
            ("sum-1", conv_id, now, now),
        )
        conn.commit()

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO conversation_summaries (id, conversation_id, summary, created_at, updated_at) "
                "VALUES (?, ?, 'summary two', ?, ?)",
                ("sum-2", conv_id, now, now),
            )
