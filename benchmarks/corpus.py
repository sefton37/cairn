"""Corpus loader for Cairn benchmark test cases.

Loads test cases from corpus.json and expands them with persona
variations using the STYLE dict from the existing harness.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CORPUS_PATH = Path(__file__).parent / "corpus.json"
PROFILES_DIR = Path(__file__).parent.parent / "tools" / "test_profiles"

# Import STYLE dict from existing harness
_HARNESS_DIR = Path(__file__).parent.parent / "tools" / "harness"
if str(_HARNESS_DIR.parent) not in sys.path:
    sys.path.insert(0, str(_HARNESS_DIR.parent))

from harness.question_generator import STYLE


@dataclass
class TestCase:
    """A single benchmark test case."""

    case_id: str
    tool_name: str
    question_template: str
    variant: str
    expected_tool: str
    expected_args_schema: dict | None
    notes: str | None

    def to_db_dict(self) -> dict[str, Any]:
        """Convert to dict for database upsert."""
        return {
            "case_id": self.case_id,
            "tool_name": self.tool_name,
            "question_template": self.question_template,
            "variant": self.variant,
            "expected_tool": self.expected_tool,
            "expected_args_schema": (
                json.dumps(self.expected_args_schema)
                if self.expected_args_schema
                else None
            ),
            "notes": self.notes,
        }


@dataclass
class PersonaProfile:
    """A synthetic persona for benchmark testing."""

    persona_id: str
    personality: str
    department: str
    role: str
    full_name: str
    db_path: str


def load_corpus(
    tool_name: str | None = None,
    variant: str | None = None,
    corpus_file: Path | None = None,
) -> list[TestCase]:
    """Load and optionally filter test cases from corpus.json.

    Args:
        tool_name: Filter to cases for this tool only.
        variant: Filter to this variant type only.
        corpus_file: Override corpus file path.

    Returns:
        List of TestCase objects.
    """
    path = corpus_file or CORPUS_PATH
    with open(path) as f:
        raw = json.load(f)

    cases = []
    for entry in raw:
        schema = entry.get("expected_args_schema")
        tc = TestCase(
            case_id=entry["case_id"],
            tool_name=entry["tool_name"],
            question_template=entry["question_template"],
            variant=entry["variant"],
            expected_tool=entry["expected_tool"],
            expected_args_schema=schema,
            notes=entry.get("notes"),
        )

        if tool_name and tc.tool_name != tool_name:
            continue
        if variant and tc.variant != variant:
            continue

        cases.append(tc)

    return cases


def load_persona_profiles(profiles_dir: Path | None = None) -> list[PersonaProfile]:
    """Load persona profiles from the test_profiles directory.

    Args:
        profiles_dir: Override profiles directory path.

    Returns:
        List of PersonaProfile objects, sorted by persona_id.
    """
    pdir = profiles_dir or PROFILES_DIR
    profiles = []

    for entry in sorted(pdir.iterdir()):
        if not entry.is_dir():
            continue
        profile_json = entry / "profile.json"
        db_file = entry / "talkingrock.db"
        if not profile_json.exists() or not db_file.exists():
            continue

        with open(profile_json) as f:
            data = json.load(f)

        identity = data.get("identity", {})
        profiles.append(
            PersonaProfile(
                persona_id=entry.name,
                personality=data.get("personality", "analytical"),
                department=identity.get("department", ""),
                role=identity.get("title", ""),
                full_name=identity.get("full_name", ""),
                db_path=str(db_file),
            )
        )

    return profiles


def style_question(question_template: str, personality: str) -> str:
    """Apply personality styling to a question template.

    Args:
        question_template: The canonical question phrasing.
        personality: Personality key (analytical, terse, verbose, etc.)

    Returns:
        Styled question text.
    """
    style_fn = STYLE.get(personality, STYLE["analytical"])
    return style_fn(question_template)


def expand_with_personas(
    cases: list[TestCase],
    profiles: list[PersonaProfile],
) -> list[tuple[TestCase, PersonaProfile, str]]:
    """Expand test cases with persona variations.

    Each case is combined with each persona profile, applying the
    persona's personality style to the question template.

    Args:
        cases: List of test cases.
        profiles: List of persona profiles.

    Returns:
        List of (case, profile, styled_prompt) triples.
    """
    expanded = []
    for case in cases:
        for profile in profiles:
            styled = style_question(case.question_template, profile.personality)
            expanded.append((case, profile, styled))
    return expanded


def get_tool_inventory() -> list[str]:
    """Get the live post-purge tool inventory from Cairn.

    Returns:
        Sorted list of tool names.
    """
    cairn_src = Path(__file__).parent.parent / "src"
    if str(cairn_src) not in sys.path:
        sys.path.insert(0, str(cairn_src))

    from cairn.cairn.mcp_tools import list_tools

    return sorted(t.name for t in list_tools())


def check_corpus_coverage(corpus_file: Path | None = None) -> dict[str, Any]:
    """Compare corpus against live tool inventory.

    Returns dict with:
        tools_total: number of live tools
        tools_covered: tools with at least one corpus case
        tools_missing: tools with no corpus cases
        orphan_cases: corpus cases for tools that no longer exist
    """
    live_tools = set(get_tool_inventory())
    cases = load_corpus(corpus_file=corpus_file)

    # Pseudo-tools (_off_topic, _ambiguous) are cross-cutting, not real tools
    pseudo_tools = {c.tool_name for c in cases if c.tool_name.startswith("_")}
    corpus_tools = {c.tool_name for c in cases} - pseudo_tools

    covered = live_tools & corpus_tools
    missing = live_tools - corpus_tools
    orphans = corpus_tools - live_tools

    return {
        "tools_total": len(live_tools),
        "tools_covered": sorted(covered),
        "tools_missing": sorted(missing),
        "orphan_cases": sorted(orphans),
        "cases_total": len(cases),
    }
