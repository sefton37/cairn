"""Temporal Context Service.

Builds a [TEMPORAL CONTEXT] block injected into every LLM prompt.
Addresses LLM temporal blindness by providing:
- Current datetime with timezone
- Last interaction timestamp and elapsed time
- Session gap detection (new vs continuing, 30-minute threshold)
- Calendar event lookahead (next 2 hours)

Zero inference cost — pure datetime math and string formatting.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta, timezone
from typing import TYPE_CHECKING

from ..play_db import _get_connection, init_db

if TYPE_CHECKING:
    from ..cairn.thunderbird import CalendarEvent

logger = logging.getLogger(__name__)

# Sessions are considered "new" after this gap
SESSION_GAP_MINUTES = 30

# Look ahead this many hours for calendar events
CALENDAR_LOOKAHEAD_HOURS = 2


def _get_local_tz() -> timezone:
    """Get the system's local timezone as a fixed-offset timezone."""
    offset = datetime.now().astimezone().utcoffset()
    assert offset is not None
    return timezone(offset)


def _format_duration(delta: timedelta) -> str:
    """Format a timedelta as a human-readable duration.

    Examples: "2 minutes", "1 hour 30 minutes", "3 hours", "1 day 4 hours"
    """
    total_seconds = int(delta.total_seconds())
    if total_seconds < 0:
        return "just now"

    days = total_seconds // 86400
    hours = (total_seconds % 86400) // 3600
    minutes = (total_seconds % 3600) // 60

    parts: list[str] = []
    if days > 0:
        parts.append(f"{days} day{'s' if days != 1 else ''}")
    if hours > 0:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    # Show at most two levels of precision:
    # days + hours, or hours + minutes, never all three.
    if minutes > 0 and days == 0:
        parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")

    return " ".join(parts) if parts else "less than a minute"


def get_last_interaction_time() -> datetime | None:
    """Get the timestamp of the most recent message in any conversation.

    Queries the messages table ordered by created_at descending.
    Returns None if no messages exist.
    """
    try:
        init_db()
        conn = _get_connection()
        cursor = conn.execute(
            "SELECT created_at FROM messages ORDER BY created_at DESC LIMIT 1"
        )
        row = cursor.fetchone()
        if row and row[0]:
            return datetime.fromisoformat(row[0])
    except Exception:
        logger.debug("Could not query last interaction time", exc_info=True)
    return None


def get_upcoming_events_text(hours: int = CALENDAR_LOOKAHEAD_HOURS) -> str | None:
    """Get formatted upcoming calendar events for the temporal context block.

    Returns a formatted string of upcoming events, or None if unavailable.
    Fails silently — calendar is optional enhancement.
    """
    try:
        from ..cairn.thunderbird import ThunderbirdBridge

        bridge = ThunderbirdBridge()
        events: list[CalendarEvent] = bridge.get_upcoming_events(hours=hours, limit=3)
        if not events:
            return None

        lines: list[str] = []
        local_tz = _get_local_tz()
        now = datetime.now(local_tz)

        for event in events:
            start = event.start
            if start.tzinfo is None:
                start = start.replace(tzinfo=local_tz)
            else:
                start = start.astimezone(local_tz)

            delta = start - now
            minutes_until = int(delta.total_seconds() / 60)

            if minutes_until <= 0:
                time_str = "now"
            elif minutes_until < 60:
                time_str = f"in {minutes_until} minute{'s' if minutes_until != 1 else ''}"
            else:
                hours_until = minutes_until // 60
                remaining_mins = minutes_until % 60
                if remaining_mins > 0:
                    time_str = (
                        f"in {hours_until} hour{'s' if hours_until != 1 else ''}"
                        f" {remaining_mins} min"
                    )
                else:
                    time_str = f"in {hours_until} hour{'s' if hours_until != 1 else ''}"

            event_time = start.strftime("%H:%M")
            lines.append(f"{event.title} at {event_time} ({time_str})")

        return "; ".join(lines)
    except Exception:
        logger.debug("Calendar lookahead unavailable", exc_info=True)
        return None


def build_temporal_context() -> str:
    """Build the [TEMPORAL CONTEXT] block for prompt injection.

    This is called on every turn. Zero inference cost — pure datetime math.

    Returns:
        Formatted temporal context string ready for prompt injection.
    """
    local_tz = _get_local_tz()
    now = datetime.now(local_tz)

    lines = [
        "[TEMPORAL CONTEXT]",
        f"Current datetime: {now.isoformat()}",
        f"Day of week: {now.strftime('%A')}",
    ]

    # Last interaction
    last_interaction = get_last_interaction_time()
    if last_interaction:
        # Ensure timezone-aware comparison
        if last_interaction.tzinfo is None:
            last_interaction = last_interaction.replace(tzinfo=UTC)
        last_local = last_interaction.astimezone(local_tz)

        delta = now - last_local
        lines.append(f"Last interaction: {last_local.isoformat()}")
        lines.append(f"Time since last interaction: {_format_duration(delta)}")

        # Session gap detection
        gap_minutes = delta.total_seconds() / 60
        session = "new" if gap_minutes > SESSION_GAP_MINUTES else "continuing"
        lines.append(f"Session: {session}")
    else:
        lines.append("Session: first")

    # Calendar lookahead
    upcoming = get_upcoming_events_text()
    if upcoming:
        lines.append(f"Upcoming: {upcoming}")

    return "\n".join(lines)
