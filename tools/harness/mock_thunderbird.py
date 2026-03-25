"""Mock ThunderbirdBridge that reads from profile DB mock tables."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from typing import Any


class MockCalendarEvent:
    """Mimics cairn.cairn.thunderbird.CalendarEvent."""

    def __init__(self, *, id: str, title: str, start: datetime, end: datetime,
                 location: str | None = None, description: str | None = None,
                 status: str | None = "CONFIRMED", all_day: bool = False,
                 is_recurring: bool = False, recurrence_rule: str | None = None,
                 recurrence_frequency: str | None = None,
                 calendar_name: str = "Personal"):
        self.id = id
        self.title = title
        self.start = start
        self.end = end
        self.location = location
        self.description = description
        self.status = status
        self.all_day = all_day
        self.is_recurring = is_recurring
        self.recurrence_rule = recurrence_rule
        self.recurrence_frequency = recurrence_frequency
        self.calendar_name = calendar_name


class MockThunderbirdBridge:
    """Drop-in replacement for ThunderbirdBridge that reads from mock tables.

    Implements the same interface as cairn.cairn.thunderbird.ThunderbirdBridge
    so CairnToolHandler can use it transparently.
    """

    def __init__(self, db_path: str):
        self.db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _row_to_event(self, row: sqlite3.Row) -> MockCalendarEvent:
        """Convert a mock_calendar_events row to a CalendarEvent-like object."""
        start = datetime.fromisoformat(row["start_time"])
        end = datetime.fromisoformat(row["end_time"])
        rrule = row["recurrence_rule"] if "recurrence_rule" in row.keys() else None

        return MockCalendarEvent(
            id=row["id"],
            title=row["title"],
            start=start,
            end=end,
            location=row["location"] or None,
            description=row["description"] or None,
            all_day=bool(row["all_day"]),
            is_recurring=rrule is not None,
            recurrence_rule=rrule,
            calendar_name=row["calendar_name"] if "calendar_name" in row.keys() else "Personal",
        )

    def is_available(self) -> bool:
        return True

    def get_status(self) -> dict[str, Any]:
        return {"available": True, "source": "mock_profile_db"}

    def list_events(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
        include_past: bool = False,
    ) -> list[MockCalendarEvent]:
        """List calendar events from mock table."""
        conn = self._connect()
        try:
            if start is None:
                start = datetime.now()
            if end is None:
                end = start + timedelta(days=30)

            query = "SELECT * FROM mock_calendar_events WHERE start_time >= ? AND start_time <= ? ORDER BY start_time"
            rows = conn.execute(query, (start.isoformat(), end.isoformat())).fetchall()

            if include_past:
                query = "SELECT * FROM mock_calendar_events WHERE start_time <= ? ORDER BY start_time"
                rows = conn.execute(query, (end.isoformat(),)).fetchall()

            return [self._row_to_event(row) for row in rows]
        finally:
            conn.close()

    def get_upcoming_events(self, hours: int = 24, limit: int = 10) -> list[MockCalendarEvent]:
        """Get upcoming events from mock table."""
        now = datetime.now()
        end = now + timedelta(hours=hours)
        events = self.list_events(start=now, end=end)
        return events[:limit]

    def get_today_events(self) -> list[MockCalendarEvent]:
        """Get today's events."""
        now = datetime.now()
        start = now.replace(hour=0, minute=0, second=0)
        end = now.replace(hour=23, minute=59, second=59)
        return self.list_events(start=start, end=end)

    def search_contacts(self, query: str, limit: int = 10) -> list:
        """No mock contacts — return empty list."""
        return []


def install_mock(db_path: str) -> MockThunderbirdBridge:
    """Monkey-patch ThunderbirdBridge.auto_detect to return our mock.

    Must be called BEFORE any CairnToolHandler is constructed.
    Returns the mock instance for reference.
    """
    mock = MockThunderbirdBridge(db_path)

    from cairn.cairn import thunderbird
    thunderbird.ThunderbirdBridge.auto_detect = classmethod(lambda cls: mock)

    return mock
