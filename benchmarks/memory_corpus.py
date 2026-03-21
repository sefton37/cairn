"""Corpus loader for Cairn memory benchmark test cases.

Loads test cases from memory_corpus.json and expands them with persona
variations using the STYLE dict from the existing harness. Style is applied
to user_message only — Cairn's voice (cairn_response) does not vary with
user personality style.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MEMORY_CORPUS_PATH = Path(__file__).parent / "memory_corpus.json"
PROFILES_DIR = Path(__file__).parent.parent / "tools" / "test_profiles"

# Import STYLE dict from existing harness
_HARNESS_DIR = Path(__file__).parent.parent / "tools" / "harness"
if str(_HARNESS_DIR.parent) not in sys.path:
    sys.path.insert(0, str(_HARNESS_DIR.parent))

from harness.question_generator import STYLE  # noqa: E402


@dataclass
class MemoryTestCase:
    """A single memory benchmark test case."""

    case_id: str
    category: str  # 'positive' | 'negative' | 'edge' | 'regression'
    # 'fact' | 'preference' | 'relationship' | 'commitment' | 'priority' | None
    memory_type: str | None
    variant: str
    user_message: str
    cairn_response: str
    expected_detection: str  # 'CREATE' | 'NO_CHANGE'
    expected_type: str | None
    expected_act_hint: str | None
    narrative_required_phrases: list[str]
    notes: str | None

    def to_db_dict(self) -> dict[str, Any]:
        """Convert to dict for database upsert."""
        return {
            "case_id": self.case_id,
            "category": self.category,
            "memory_type": self.memory_type,
            "variant": self.variant,
            "user_message": self.user_message,
            "cairn_response": self.cairn_response,
            "expected_detection": self.expected_detection,
            "expected_type": self.expected_type,
            "expected_act_hint": self.expected_act_hint,
            "narrative_required_phrases": json.dumps(self.narrative_required_phrases),
            "notes": self.notes,
        }


def load_memory_corpus(
    category: str | None = None,
    memory_type: str | None = None,
    corpus_file: Path | None = None,
) -> list[MemoryTestCase]:
    """Load and optionally filter memory test cases from memory_corpus.json.

    Args:
        category: Filter to cases in this category ('positive', 'negative',
            'edge', 'regression').
        memory_type: Filter to cases with this memory_type ('fact',
            'preference', 'relationship', 'commitment', 'priority').
        corpus_file: Override corpus file path.

    Returns:
        List of MemoryTestCase objects matching the filters.
    """
    path = corpus_file or MEMORY_CORPUS_PATH
    with open(path) as f:
        raw = json.load(f)

    cases = []
    for entry in raw:
        tc = MemoryTestCase(
            case_id=entry["case_id"],
            category=entry["category"],
            memory_type=entry.get("memory_type"),
            variant=entry["variant"],
            user_message=entry["user_message"],
            cairn_response=entry["cairn_response"],
            expected_detection=entry["expected_detection"],
            expected_type=entry.get("expected_type"),
            expected_act_hint=entry.get("expected_act_hint"),
            narrative_required_phrases=entry.get("narrative_required_phrases", []),
            notes=entry.get("notes"),
        )

        if category and tc.category != category:
            continue
        if memory_type and tc.memory_type != memory_type:
            continue

        cases.append(tc)

    return cases


def expand_memory_with_personas(
    cases: list[MemoryTestCase],
    profiles: list[Any],
    styles: dict[str, Any] | None = None,
) -> list[tuple[MemoryTestCase, Any, str]]:
    """Expand memory test cases with persona variations.

    Applies personality styling to user_message ONLY. cairn_response is left
    unchanged — Cairn's voice should not vary with user personality style.

    Each case is combined with each persona profile, applying the persona's
    personality style to the user_message.

    Args:
        cases: List of MemoryTestCase objects.
        profiles: List of PersonaProfile objects (from corpus.load_persona_profiles).
        styles: Optional STYLE dict override. Uses harness STYLE by default.

    Returns:
        List of (case, profile, styled_user_message) triples.
    """
    style_dict = styles if styles is not None else STYLE
    expanded = []
    for case in cases:
        for profile in profiles:
            personality = getattr(profile, "personality", "analytical")
            style_fn = style_dict.get(personality, style_dict.get("analytical", lambda x: x))
            styled_user_message = style_fn(case.user_message)
            expanded.append((case, profile, styled_user_message))
    return expanded


def upsert_memory_test_cases(
    conn: sqlite3.Connection,
    cases: list[MemoryTestCase],
) -> int:
    """Insert or update memory test cases in the benchmark database.

    Uses INSERT OR REPLACE so re-running with the same corpus is idempotent.

    Args:
        conn: Open SQLite connection to the benchmark database.
        cases: List of MemoryTestCase objects to upsert.

    Returns:
        Number of cases written.
    """
    rows = [c.to_db_dict() for c in cases]
    conn.executemany(
        """
        INSERT OR REPLACE INTO memory_test_cases (
            case_id, category, memory_type, variant,
            user_message, cairn_response,
            expected_detection, expected_type, expected_act_hint,
            narrative_required_phrases, notes
        ) VALUES (
            :case_id, :category, :memory_type, :variant,
            :user_message, :cairn_response,
            :expected_detection, :expected_type, :expected_act_hint,
            :narrative_required_phrases, :notes
        )
        """,
        rows,
    )
    conn.commit()
    return len(rows)
