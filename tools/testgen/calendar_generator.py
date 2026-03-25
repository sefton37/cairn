"""Generate realistic mock calendar events for each profile."""

from __future__ import annotations

import json
import random
import uuid
from datetime import datetime, timedelta

BASE_DATE = datetime(2026, 3, 13, 9, 0, 0)


def _next_weekday(start: datetime, weekday: int) -> datetime:
    """Find next occurrence of weekday (0=Monday) from start."""
    days_ahead = weekday - start.weekday()
    if days_ahead <= 0:
        days_ahead += 7
    return start + timedelta(days=days_ahead)


def generate_calendar_events(profile: dict) -> list[dict]:
    """Generate 30 realistic calendar events spread across 2 weeks."""
    dept = profile["identity"]["department"].lower()
    full_name = profile["identity"]["full_name"]
    act_titles = [a["title"] for a in profile["acts"]]

    events = []
    used_slots = set()  # (date_str, hour) to avoid double-booking

    def _slot_free(dt: datetime) -> bool:
        key = (dt.strftime("%Y-%m-%d"), dt.hour)
        if key in used_slots:
            return False
        used_slots.add(key)
        return True

    def _add(title, start, end, location="", desc="", cal="Work",
             all_day=False, recurrence=None, attendees=None):
        events.append({
            "id": f"cal-{uuid.uuid4()}",
            "title": title,
            "start_time": start.isoformat(),
            "end_time": end.isoformat(),
            "location": location,
            "description": desc,
            "calendar_name": cal,
            "all_day": 1 if all_day else 0,
            "recurrence_rule": recurrence,
            "attendees": json.dumps(attendees or []),
        })

    # --- Recurring events (both weeks) ---

    for week_offset in range(2):
        week_start = BASE_DATE + timedelta(weeks=week_offset)

        # Daily standup (Mon-Fri)
        for d in range(5):
            day = week_start + timedelta(days=(0 - week_start.weekday() + d))
            if day < BASE_DATE:
                continue
            dt = day.replace(hour=9, minute=15)
            if _slot_free(dt):
                _add(
                    f"{dept.title()} Daily Standup",
                    dt, dt + timedelta(minutes=15),
                    location="Zoom",
                    recurrence="FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR",
                    attendees=["team"],
                )

        # Weekly 1:1 with manager
        day_11 = _next_weekday(week_start - timedelta(days=7), random.choice([1, 2, 3]))
        if day_11 >= BASE_DATE:
            dt = day_11.replace(hour=14, minute=0)
            if _slot_free(dt):
                _add(
                    "1:1 with Manager",
                    dt, dt + timedelta(minutes=30),
                    location="Manager's Office",
                    recurrence="FREQ=WEEKLY",
                )

        # Weekly team meeting
        team_day = _next_weekday(week_start - timedelta(days=7), 1)  # Tuesday
        if team_day >= BASE_DATE:
            dt = team_day.replace(hour=10, minute=0)
            if _slot_free(dt):
                _add(
                    f"{dept.title()} Team Meeting",
                    dt, dt + timedelta(hours=1),
                    location="Conference Room B",
                    recurrence="FREQ=WEEKLY",
                    attendees=["team"],
                )

    # --- One-time events ---

    # Company all-hands (Friday of week 1)
    ah_day = _next_weekday(BASE_DATE - timedelta(days=7), 4)
    if ah_day >= BASE_DATE:
        dt = ah_day.replace(hour=16, minute=0)
        if _slot_free(dt):
            _add(
                "Company All-Hands",
                dt, dt + timedelta(hours=1),
                location="Main Hall / Zoom",
                desc="Q1 recap and Q2 preview from leadership",
                attendees=["all@meridian-labs.com"],
            )

    # Project-specific meetings (2-3 per act)
    for act in profile["acts"]:
        for j in range(random.randint(2, 3)):
            day_offset = random.randint(0, 13)
            day = BASE_DATE + timedelta(days=day_offset)
            # Skip weekends
            while day.weekday() >= 5:
                day += timedelta(days=1)
            hour = random.choice([10, 11, 13, 14, 15, 16])
            dt = day.replace(hour=hour, minute=0)
            if _slot_free(dt):
                titles = [
                    f"{act['title']} — Sprint Review",
                    f"{act['title']} — Design Review",
                    f"{act['title']} — Planning",
                    f"{act['title']} — Stakeholder Sync",
                    f"{act['title']} — Tech Review",
                ]
                _add(
                    random.choice(titles),
                    dt, dt + timedelta(minutes=random.choice([30, 45, 60])),
                    location=random.choice(["Zoom", "Conference Room A", "Huddle Room 3"]),
                    desc=f"Review progress on {act['title']}",
                )

    # Cross-functional meetings
    xfunc_meetings = [
        "Cross-Team Sync: Engineering × Product",
        "Leadership Update",
        "OKR Check-in",
        "Architecture Review",
        "Security Review",
        "Budget Review",
        "Hiring Pipeline Review",
        "Customer Feedback Review",
    ]
    for _ in range(random.randint(3, 5)):
        day_offset = random.randint(0, 13)
        day = BASE_DATE + timedelta(days=day_offset)
        while day.weekday() >= 5:
            day += timedelta(days=1)
        hour = random.choice([10, 11, 13, 14, 15])
        dt = day.replace(hour=hour, minute=0)
        if _slot_free(dt):
            _add(
                random.choice(xfunc_meetings),
                dt, dt + timedelta(minutes=random.choice([30, 60])),
                location="Zoom",
            )

    # Lunch / personal
    for _ in range(random.randint(1, 3)):
        day_offset = random.randint(0, 13)
        day = BASE_DATE + timedelta(days=day_offset)
        while day.weekday() >= 5:
            day += timedelta(days=1)
        dt = day.replace(hour=12, minute=0)
        if _slot_free(dt):
            _add(
                random.choice(["Lunch with Team", "Coffee Chat", "Walking Meeting"]),
                dt, dt + timedelta(minutes=60),
                location=random.choice(["Café Nero", "Courtyard", ""]),
                cal="Personal",
            )

    # Focus time blocks
    for _ in range(random.randint(2, 4)):
        day_offset = random.randint(0, 13)
        day = BASE_DATE + timedelta(days=day_offset)
        while day.weekday() >= 5:
            day += timedelta(days=1)
        hour = random.choice([9, 10, 13, 14])
        dt = day.replace(hour=hour, minute=0)
        if _slot_free(dt):
            _add(
                "Focus Time — Do Not Disturb",
                dt, dt + timedelta(hours=2),
                desc="Deep work block",
            )

    # External meetings (vendor calls, interviews, etc.)
    external_meetings = [
        "Vendor Call: AWS Account Review",
        "Interview: Senior Engineer Candidate",
        "Partner Sync: Acme Corp Integration",
        "Analyst Briefing",
        "Customer Call: Hartfield Industries",
        "Recruiter Screen",
    ]
    for _ in range(random.randint(2, 3)):
        day_offset = random.randint(0, 13)
        day = BASE_DATE + timedelta(days=day_offset)
        while day.weekday() >= 5:
            day += timedelta(days=1)
        hour = random.choice([10, 11, 14, 15, 16])
        dt = day.replace(hour=hour, minute=0)
        if _slot_free(dt):
            _add(
                random.choice(external_meetings),
                dt, dt + timedelta(minutes=random.choice([30, 45, 60])),
                location="Zoom",
            )

    # Pad to 30 if we don't have enough
    while len(events) < 30:
        day_offset = random.randint(0, 13)
        day = BASE_DATE + timedelta(days=day_offset)
        while day.weekday() >= 5:
            day += timedelta(days=1)
        hour = random.choice([9, 10, 11, 13, 14, 15, 16, 17])
        dt = day.replace(hour=hour, minute=0)
        if _slot_free(dt):
            _add(
                random.choice([
                    "Catch-up", "Brainstorm Session", "Sprint Retro",
                    "Documentation Review", "Code Review Session",
                    "Quarterly Planning Prep", "Process Improvement",
                    "Knowledge Sharing", "Tech Talk", "Demo",
                ]),
                dt, dt + timedelta(minutes=random.choice([30, 45, 60])),
                location=random.choice(["Zoom", "Conference Room A", ""]),
            )

    events.sort(key=lambda e: e["start_time"])
    return events[:30]
