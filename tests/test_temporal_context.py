"""Tests for temporal context injection.

Verifies:
- Temporal context block is generated with correct format
- Last interaction time is queried from messages table
- Session gap detection (new vs continuing, 30-minute threshold)
- Duration formatting is human-readable
- Calendar event lookahead is included when available
- Graceful fallback when DB or calendar is unavailable
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from reos.play_db import (
    _get_connection,
    close_connection,
    init_db,
)
from reos.services.temporal_context import (
    SESSION_GAP_MINUTES,
    _format_duration,
    _get_local_tz,
    build_temporal_context,
    get_last_interaction_time,
    get_upcoming_events_text,
)


@pytest.fixture(autouse=True)
def _fresh_db(tmp_path, monkeypatch):
    """Use a fresh temporary database for each test."""
    monkeypatch.setenv("REOS_DATA_DIR", str(tmp_path))
    close_connection()
    init_db()
    yield
    close_connection()


def _insert_message(conn: sqlite3.Connection, created_at: str) -> None:
    """Insert a message with the given timestamp for testing."""
    now = "2026-01-01T00:00:00+00:00"
    act_id = "your-story"
    conv_block_id = f"block-{uuid.uuid4().hex[:12]}"
    msg_block_id = f"block-{uuid.uuid4().hex[:12]}"
    conv_id = uuid.uuid4().hex[:12]
    msg_id = uuid.uuid4().hex[:12]

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
    conn.execute(
        "INSERT INTO messages (id, conversation_id, block_id, role, content, position, created_at) "
        "VALUES (?, ?, ?, 'user', 'test message', 0, ?)",
        (msg_id, conv_id, msg_block_id, created_at),
    )
    conn.commit()


class TestFormatDuration:
    """Test human-readable duration formatting."""

    def test_less_than_a_minute(self):
        assert _format_duration(timedelta(seconds=30)) == "less than a minute"

    def test_one_minute(self):
        assert _format_duration(timedelta(minutes=1)) == "1 minute"

    def test_multiple_minutes(self):
        assert _format_duration(timedelta(minutes=45)) == "45 minutes"

    def test_one_hour(self):
        assert _format_duration(timedelta(hours=1)) == "1 hour"

    def test_hours_and_minutes(self):
        assert _format_duration(timedelta(hours=2, minutes=30)) == "2 hours 30 minutes"

    def test_days_and_hours(self):
        result = _format_duration(timedelta(days=1, hours=4))
        assert "1 day" in result
        assert "4 hours" in result

    def test_days_only(self):
        assert _format_duration(timedelta(days=2)) == "2 days"

    def test_one_day_no_hours(self):
        assert _format_duration(timedelta(days=1)) == "1 day"

    def test_negative_returns_just_now(self):
        assert _format_duration(timedelta(seconds=-5)) == "just now"

    def test_zero_duration(self):
        assert _format_duration(timedelta(0)) == "less than a minute"


class TestGetLastInteractionTime:
    """Test querying last message timestamp from DB."""

    def test_no_messages_returns_none(self):
        assert get_last_interaction_time() is None

    def test_returns_most_recent_message(self):
        conn = _get_connection()
        _insert_message(conn, "2026-02-28T06:00:00+00:00")
        _insert_message(conn, "2026-02-28T08:00:00+00:00")

        result = get_last_interaction_time()
        assert result is not None
        assert result.hour == 8


class TestBuildTemporalContext:
    """Test the main temporal context block builder."""

    def test_contains_header(self):
        result = build_temporal_context()
        assert "[TEMPORAL CONTEXT]" in result

    def test_contains_current_datetime(self):
        result = build_temporal_context()
        assert "Current datetime:" in result

    def test_contains_day_of_week(self):
        result = build_temporal_context()
        # Should contain a valid day name
        days = {"Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"}
        assert any(f"Day of week: {day}" in result for day in days)

    def test_first_session_when_no_messages(self):
        result = build_temporal_context()
        assert "Session: first" in result

    def test_continuing_session_recent_message(self):
        """A message 5 minutes ago should be a continuing session."""
        conn = _get_connection()
        recent = datetime.now(UTC) - timedelta(minutes=5)
        _insert_message(conn, recent.isoformat())

        result = build_temporal_context()
        assert "Session: continuing" in result
        assert "Last interaction:" in result
        assert "Time since last interaction:" in result

    def test_new_session_after_gap(self):
        """A message 2 hours ago should be a new session."""
        conn = _get_connection()
        old = datetime.now(UTC) - timedelta(hours=2)
        _insert_message(conn, old.isoformat())

        result = build_temporal_context()
        assert "Session: new" in result

    def test_session_gap_boundary(self):
        """Exactly at the gap threshold should be continuing."""
        conn = _get_connection()
        # Just under the threshold
        recent = datetime.now(UTC) - timedelta(minutes=SESSION_GAP_MINUTES - 1)
        _insert_message(conn, recent.isoformat())

        result = build_temporal_context()
        assert "Session: continuing" in result

    def test_session_gap_just_over(self):
        """Just over the gap threshold should be new."""
        conn = _get_connection()
        old = datetime.now(UTC) - timedelta(minutes=SESSION_GAP_MINUTES + 1)
        _insert_message(conn, old.isoformat())

        result = build_temporal_context()
        assert "Session: new" in result

    def test_calendar_included_when_available(self):
        """Calendar events should appear in temporal context when available."""
        mock_event = MagicMock()
        mock_event.title = "Team standup"
        mock_event.start = datetime.now() + timedelta(minutes=15)

        with patch(
            "reos.services.temporal_context.get_upcoming_events_text",
            return_value="Team standup at 09:00 (in 15 minutes)",
        ):
            result = build_temporal_context()
            assert "Upcoming:" in result
            assert "Team standup" in result

    def test_no_calendar_still_works(self):
        """Temporal context works without calendar integration."""
        with patch(
            "reos.services.temporal_context.get_upcoming_events_text",
            return_value=None,
        ):
            result = build_temporal_context()
            assert "[TEMPORAL CONTEXT]" in result
            assert "Upcoming:" not in result


class TestGetLocalTz:
    """Test timezone detection."""

    def test_returns_timezone(self):
        tz = _get_local_tz()
        assert isinstance(tz, timezone)

    def test_offset_is_reasonable(self):
        tz = _get_local_tz()
        offset = tz.utcoffset(None)
        assert offset is not None
        # UTC offset should be between -12 and +14 hours
        hours = offset.total_seconds() / 3600
        assert -12 <= hours <= 14


class TestGetUpcomingEventsText:
    """Test calendar event formatting."""

    def test_no_bridge_returns_none(self):
        """When ThunderbirdBridge is unavailable, returns None."""
        with patch(
            "reos.cairn.thunderbird.ThunderbirdBridge",
            side_effect=Exception("no thunderbird"),
        ):
            result = get_upcoming_events_text()
            assert result is None

    def test_no_events_returns_none(self):
        """No upcoming events returns None."""
        mock_bridge = MagicMock()
        mock_bridge.get_upcoming_events.return_value = []

        with patch(
            "reos.cairn.thunderbird.ThunderbirdBridge",
            return_value=mock_bridge,
        ):
            result = get_upcoming_events_text()
            assert result is None

    def test_formats_single_event(self):
        """A single upcoming event is formatted correctly."""
        local_tz = _get_local_tz()
        event = MagicMock()
        event.title = "Team standup"
        event.start = datetime.now(local_tz) + timedelta(minutes=15)

        mock_bridge = MagicMock()
        mock_bridge.get_upcoming_events.return_value = [event]

        with patch(
            "reos.cairn.thunderbird.ThunderbirdBridge",
            return_value=mock_bridge,
        ):
            result = get_upcoming_events_text()
            assert result is not None
            assert "Team standup" in result
            assert "minute" in result

    def test_formats_multiple_events(self):
        """Multiple events are separated by semicolons."""
        local_tz = _get_local_tz()
        event1 = MagicMock()
        event1.title = "Standup"
        event1.start = datetime.now(local_tz) + timedelta(minutes=15)

        event2 = MagicMock()
        event2.title = "Design review"
        event2.start = datetime.now(local_tz) + timedelta(hours=1, minutes=30)

        mock_bridge = MagicMock()
        mock_bridge.get_upcoming_events.return_value = [event1, event2]

        with patch(
            "reos.cairn.thunderbird.ThunderbirdBridge",
            return_value=mock_bridge,
        ):
            result = get_upcoming_events_text()
            assert result is not None
            assert "Standup" in result
            assert "Design review" in result
            assert ";" in result


class TestAgentIntegration:
    """Test that temporal context integrates into the prompt pipeline."""

    def test_temporal_context_field_on_conversation_context(self):
        """ConversationContext has a temporal_context field."""
        from reos.agent import ConversationContext

        ctx = ConversationContext(
            user_text="test",
            conversation_id="test-123",
            temporal_context="[TEMPORAL CONTEXT]\nCurrent datetime: 2026-02-28T06:34:00-06:00",
        )
        assert "[TEMPORAL CONTEXT]" in ctx.temporal_context

    def test_temporal_context_is_first_in_prompt(self):
        """Temporal context appears before persona system in prompt prefix."""
        from reos.agent import ConversationContext

        ctx = ConversationContext(
            user_text="test",
            conversation_id="test-123",
            temporal_context="[TEMPORAL CONTEXT]\nTest temporal",
            persona_system="You are CAIRN.",
        )
        prefix = ctx.build_prompt_prefix()
        tc_pos = prefix.index("[TEMPORAL CONTEXT]")
        persona_pos = prefix.index("You are CAIRN.")
        assert tc_pos < persona_pos

    def test_no_temporal_context_still_works(self):
        """Empty temporal_context doesn't add garbage to prompt."""
        from reos.agent import ConversationContext

        ctx = ConversationContext(
            user_text="test",
            conversation_id="test-123",
            temporal_context="",
            persona_system="You are CAIRN.",
        )
        prefix = ctx.build_prompt_prefix()
        assert prefix.startswith("You are CAIRN.")
