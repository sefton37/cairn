"""Generate per-persona question sets from profile DB data."""

from __future__ import annotations

import random
import sqlite3
from pathlib import Path

# Personality → question phrasing style
STYLE = {
    "analytical": lambda q: q,  # precise as-is
    "terse": lambda q: q.rstrip("?").rstrip(".").split(",")[0].strip() + "?",  # trim to shortest
    "verbose": lambda q: f"I was just thinking about this — {q.lower()} I'd really appreciate a thorough answer.",
    "anxious": lambda q: f"Hey, I'm a bit worried — {q.lower()} Can you help?",
    "creative": lambda q: f"Oh! Random thought — {q.lower()} Also curious what you think.",
    "methodical": lambda q: q,  # clean and direct
}

# Terse overrides: completely rewritten short versions
TERSE_OVERRIDES = {
    "calendar": ["Calendar today?", "Schedule?", "What's next?", "Meetings?"],
    "email": ["Urgent emails?", "Inbox status?", "New mail?"],
    "project": None,  # filled at runtime
    "task": ["Priorities?", "Next task?", "What's urgent?"],
    "personal": ["About me?", "My background?"],
    "vague": ["stuff", "help", "???", "things"],
    "multi_intent": None,  # filled at runtime
    "off_topic": ["Weather?", "Sports scores?", "Recipe for pasta?"],
}

# Standard question templates by type
TEMPLATES = {
    "calendar": [
        "What's on my calendar today?",
        "What meetings do I have this week?",
        "Do I have any conflicts on my calendar?",
        "What's my schedule look like for the next few days?",
        "Am I free this afternoon?",
    ],
    "email": [
        "Any urgent emails I should know about?",
        "What are my most important unread emails?",
        "Did I get any emails from leadership?",
        "Summarize my recent emails.",
        "Any emails about {subject}?",
    ],
    "project": [
        "What's the status of {act_title}?",
        "Give me an update on {act_title}.",
        "What are the blockers on {act_title}?",
        "How is {act_title} progressing?",
        "What's left to do on {act_title}?",
    ],
    "task": [
        "What should I work on next?",
        "What are my priorities right now?",
        "What tasks need my attention?",
        "What's the most important thing I should focus on?",
        "Do I have any overdue tasks?",
    ],
    "personal": [
        "Tell me about myself.",
        "What do you know about me?",
        "Summarize my background.",
        "What are my key responsibilities?",
    ],
    "vague": [
        "stuff",
        "help",
        "???",
        "what should I do",
        "things",
        "um",
        "idk",
    ],
    "multi_intent": [
        "Check my calendar and tell me about {act_title}.",
        "Any urgent emails? Also what's the status of {act_title}?",
        "What meetings do I have today and what should I prioritize?",
    ],
    "off_topic": [
        "What's the weather like in Tokyo?",
        "Tell me a joke.",
        "What's the capital of France?",
        "How do I make sourdough bread?",
        "What's the meaning of life?",
    ],
}

QUERY_TYPES = [
    "calendar", "email", "project", "task",
    "personal", "vague", "multi_intent", "off_topic",
]


def _load_profile_data(db_path: str) -> dict:
    """Load act titles and sample data from profile DB."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Get user acts (not system acts)
    acts = conn.execute(
        "SELECT act_id, title FROM acts WHERE system_role IS NULL ORDER BY position"
    ).fetchall()
    act_titles = [row["title"] for row in acts]

    # Get a sample email subject
    email_row = conn.execute(
        "SELECT subject FROM mock_emails WHERE is_read = 0 ORDER BY date DESC LIMIT 1"
    ).fetchone()
    email_subject = email_row["subject"] if email_row else "project updates"

    conn.close()
    return {"act_titles": act_titles, "email_subject": email_subject}


def generate_questions(
    profile_id: str,
    profile_data: dict,
    db_path: str,
    seed: int | None = None,
) -> list[dict]:
    """Generate 8 questions for a profile, one per query type.

    Args:
        profile_id: Profile identifier.
        profile_data: Profile dict with personality field.
        db_path: Path to profile's talkingrock.db.
        seed: Random seed for deterministic generation.

    Returns:
        List of question dicts with question_id, query_type, text, profile_id.
    """
    rng = random.Random(seed or hash(profile_id))
    personality = profile_data.get("personality", "analytical")
    style_fn = STYLE.get(personality, STYLE["analytical"])

    # Load data from the DB for template filling
    data = _load_profile_data(db_path)
    act_titles = data["act_titles"]
    email_subject = data["email_subject"]

    if not act_titles:
        act_titles = ["my main project"]

    questions = []

    for i, qtype in enumerate(QUERY_TYPES):
        templates = TEMPLATES[qtype]
        template = rng.choice(templates)

        # Fill templates
        text = template
        if "{act_title}" in text:
            text = text.replace("{act_title}", rng.choice(act_titles))
        if "{subject}" in text:
            text = text.replace("{subject}", email_subject)

        # Apply personality style
        if personality == "terse" and qtype in TERSE_OVERRIDES:
            overrides = TERSE_OVERRIDES[qtype]
            if overrides:
                text = rng.choice(overrides)
            else:
                # For project/multi_intent, shorten the filled text
                text = text.split("?")[0].strip() + "?"
                if len(text) > 40:
                    text = text[:37] + "...?"
        elif personality != "terse":
            text = style_fn(text)

        questions.append({
            "question_id": f"q-{profile_id}-{i:02d}-{qtype}",
            "query_type": qtype,
            "text": text,
            "profile_id": profile_id,
        })

    return questions


def generate_extended_questions(
    profile_id: str,
    profile_data: dict,
    db_path: str,
    count: int = 20,
    seed: int | None = None,
) -> list[dict]:
    """Generate a larger set of varied questions for deeper testing.

    Generates `count` questions by cycling through types with variation.
    """
    rng = random.Random(seed or hash(profile_id))
    personality = profile_data.get("personality", "analytical")
    style_fn = STYLE.get(personality, STYLE["analytical"])
    data = _load_profile_data(db_path)
    act_titles = data["act_titles"] or ["my main project"]
    email_subject = data["email_subject"]

    questions = []
    for i in range(count):
        qtype = QUERY_TYPES[i % len(QUERY_TYPES)]
        templates = TEMPLATES[qtype]
        template = rng.choice(templates)

        text = template
        if "{act_title}" in text:
            text = text.replace("{act_title}", rng.choice(act_titles))
        if "{subject}" in text:
            text = text.replace("{subject}", email_subject)

        if personality == "terse":
            overrides = TERSE_OVERRIDES.get(qtype)
            if overrides:
                text = rng.choice(overrides)
        else:
            text = style_fn(text)

        questions.append({
            "question_id": f"q-{profile_id}-{i:02d}-{qtype}",
            "query_type": qtype,
            "text": text,
            "profile_id": profile_id,
        })

    return questions
