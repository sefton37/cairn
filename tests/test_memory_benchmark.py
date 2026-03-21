"""Unit tests for memory benchmark corpus loader and scoring functions.

Tests cover:
    - Corpus loading (count, field mapping, filtering)
    - expand_memory_with_personas (style applied to user_message only)
    - All five scoring function branches in memory_matching
"""

from __future__ import annotations

import json
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Add project root to sys.path so that 'benchmarks' is importable without
# requiring the caller to include '.' in PYTHONPATH.
_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

MEMORY_CORPUS_PATH = Path(__file__).parent.parent / "benchmarks" / "memory_corpus.json"

# Minimal STYLE dict that prefixes messages with the personality key for easy
# assertion in tests — no real harness dependency needed.
_TEST_STYLE: dict[str, Any] = {
    "analytical": lambda q: q,
    "terse": lambda q: f"[terse] {q}",
    "verbose": lambda q: f"[verbose] {q}",
    "anxious": lambda q: f"[anxious] {q}",
    "creative": lambda q: f"[creative] {q}",
    "methodical": lambda q: q,
}


@dataclass
class _MockProfile:
    """Minimal persona profile for testing expand_memory_with_personas."""

    persona_id: str
    personality: str
    db_path: str = "/tmp/fake.db"


# ---------------------------------------------------------------------------
# Corpus loading tests
# ---------------------------------------------------------------------------


class TestLoadMemoryCorpus:
    def test_total_case_count(self) -> None:
        """Corpus must contain exactly 42 cases."""
        from benchmarks.memory_corpus import load_memory_corpus

        cases = load_memory_corpus()
        assert len(cases) == 42

    def test_returns_memory_test_case_objects(self) -> None:
        """load_memory_corpus returns MemoryTestCase dataclass instances."""
        from benchmarks.memory_corpus import MemoryTestCase, load_memory_corpus

        cases = load_memory_corpus()
        assert all(isinstance(c, MemoryTestCase) for c in cases)

    def test_required_fields_populated(self) -> None:
        """Every case has non-empty mandatory fields."""
        from benchmarks.memory_corpus import load_memory_corpus

        cases = load_memory_corpus()
        for case in cases:
            assert case.case_id, f"case_id empty for {case}"
            assert case.category in {"positive", "negative", "edge", "regression"}
            assert case.variant
            assert case.user_message
            assert case.cairn_response
            assert case.expected_detection in {"CREATE", "NO_CHANGE"}

    def test_narrative_required_phrases_is_list(self) -> None:
        """narrative_required_phrases is always a list, never None."""
        from benchmarks.memory_corpus import load_memory_corpus

        cases = load_memory_corpus()
        for case in cases:
            assert isinstance(case.narrative_required_phrases, list)

    def test_filter_by_category_positive(self) -> None:
        """Filtering by category='positive' returns only positive cases."""
        from benchmarks.memory_corpus import load_memory_corpus

        cases = load_memory_corpus(category="positive")
        assert len(cases) == 30
        assert all(c.category == "positive" for c in cases)

    def test_filter_by_category_negative(self) -> None:
        """Filtering by category='negative' returns only negative cases."""
        from benchmarks.memory_corpus import load_memory_corpus

        cases = load_memory_corpus(category="negative")
        assert len(cases) == 6
        assert all(c.category == "negative" for c in cases)

    def test_filter_by_memory_type_fact(self) -> None:
        """Filtering by memory_type='fact' returns only fact cases."""
        from benchmarks.memory_corpus import load_memory_corpus

        cases = load_memory_corpus(memory_type="fact")
        assert len(cases) > 0
        assert all(c.memory_type == "fact" for c in cases)

    def test_filter_by_memory_type_commitment(self) -> None:
        """Filtering by memory_type='commitment' returns only commitment cases."""
        from benchmarks.memory_corpus import load_memory_corpus

        cases = load_memory_corpus(memory_type="commitment")
        assert len(cases) > 0
        assert all(c.memory_type == "commitment" for c in cases)

    def test_filter_by_both_category_and_type(self) -> None:
        """Both filters applied together are ANDed."""
        from benchmarks.memory_corpus import load_memory_corpus

        cases = load_memory_corpus(category="positive", memory_type="preference")
        assert len(cases) > 0
        assert all(c.category == "positive" and c.memory_type == "preference" for c in cases)

    def test_filter_returns_empty_list_for_no_match(self) -> None:
        """Filtering with no matching cases returns an empty list, not an error."""
        from benchmarks.memory_corpus import load_memory_corpus

        # Negative cases have memory_type=None, so filtering negative+fact yields nothing.
        cases = load_memory_corpus(category="negative", memory_type="fact")
        assert cases == []

    def test_custom_corpus_file(self, tmp_path: Path) -> None:
        """corpus_file parameter loads from an alternate path."""
        from benchmarks.memory_corpus import load_memory_corpus

        custom = [
            {
                "case_id": "custom_01",
                "category": "positive",
                "memory_type": "fact",
                "variant": "basic",
                "user_message": "I work remotely.",
                "cairn_response": "Noted.",
                "expected_detection": "CREATE",
                "expected_type": "fact",
                "expected_act_hint": None,
                "narrative_required_phrases": ["remotely"],
                "notes": "custom test",
            }
        ]
        custom_path = tmp_path / "custom_corpus.json"
        custom_path.write_text(json.dumps(custom))

        cases = load_memory_corpus(corpus_file=custom_path)
        assert len(cases) == 1
        assert cases[0].case_id == "custom_01"

    def test_negative_cases_have_null_expected_type(self) -> None:
        """All NO_CHANGE cases should have expected_type=None."""
        from benchmarks.memory_corpus import load_memory_corpus

        cases = load_memory_corpus()
        for case in cases:
            if case.expected_detection == "NO_CHANGE":
                assert case.expected_type is None, (
                    f"{case.case_id} has expected_detection=NO_CHANGE but "
                    f"expected_type={case.expected_type!r}"
                )

    def test_to_db_dict_serializes_phrases_as_json(self) -> None:
        """to_db_dict() encodes narrative_required_phrases as a JSON string."""
        from benchmarks.memory_corpus import load_memory_corpus

        cases = load_memory_corpus(memory_type="fact")
        db_dict = cases[0].to_db_dict()
        assert isinstance(db_dict["narrative_required_phrases"], str)
        decoded = json.loads(db_dict["narrative_required_phrases"])
        assert isinstance(decoded, list)


# ---------------------------------------------------------------------------
# expand_memory_with_personas tests
# ---------------------------------------------------------------------------


class TestExpandMemoryWithPersonas:
    def _get_two_cases(self) -> list[Any]:
        from benchmarks.memory_corpus import load_memory_corpus

        return load_memory_corpus()[:2]

    def test_expansion_count(self) -> None:
        """Returns cases × profiles triples."""
        from benchmarks.memory_corpus import expand_memory_with_personas

        cases = self._get_two_cases()
        profiles = [
            _MockProfile("p1", "analytical"),
            _MockProfile("p2", "terse"),
            _MockProfile("p3", "verbose"),
        ]
        expanded = expand_memory_with_personas(cases, profiles, styles=_TEST_STYLE)
        assert len(expanded) == len(cases) * len(profiles)

    def test_triple_structure(self) -> None:
        """Each element is a (MemoryTestCase, profile, styled_str) triple."""
        from benchmarks.memory_corpus import MemoryTestCase, expand_memory_with_personas

        cases = self._get_two_cases()
        profiles = [_MockProfile("p1", "analytical")]
        expanded = expand_memory_with_personas(cases, profiles, styles=_TEST_STYLE)

        case, profile, styled = expanded[0]
        assert isinstance(case, MemoryTestCase)
        assert profile.persona_id == "p1"
        assert isinstance(styled, str)

    def test_style_applied_to_user_message_only(self) -> None:
        """Styling changes the user_message but cairn_response is untouched."""
        from benchmarks.memory_corpus import expand_memory_with_personas, load_memory_corpus

        cases = load_memory_corpus()[:1]
        profiles = [_MockProfile("p1", "terse")]
        expanded = expand_memory_with_personas(cases, profiles, styles=_TEST_STYLE)

        case, profile, styled_user_message = expanded[0]
        # The terse style in our test dict prefixes with "[terse] "
        assert styled_user_message.startswith("[terse] ")
        # cairn_response on the original case must be unchanged
        assert case.cairn_response == cases[0].cairn_response

    def test_analytical_style_leaves_message_unchanged(self) -> None:
        """'analytical' style returns the original user_message unmodified."""
        from benchmarks.memory_corpus import expand_memory_with_personas, load_memory_corpus

        cases = load_memory_corpus()[:1]
        profiles = [_MockProfile("p1", "analytical")]
        expanded = expand_memory_with_personas(cases, profiles, styles=_TEST_STYLE)

        case, _profile, styled = expanded[0]
        assert styled == case.user_message

    def test_unknown_personality_falls_back_to_analytical(self) -> None:
        """An unrecognised personality key falls back gracefully."""
        from benchmarks.memory_corpus import expand_memory_with_personas, load_memory_corpus

        cases = load_memory_corpus()[:1]
        profiles = [_MockProfile("p1", "unknown_personality")]
        # Should not raise — falls back to identity function
        expanded = expand_memory_with_personas(cases, profiles, styles=_TEST_STYLE)
        _case, _profile, styled = expanded[0]
        assert isinstance(styled, str)

    def test_empty_profiles_returns_empty_list(self) -> None:
        """No profiles → no expansions."""
        from benchmarks.memory_corpus import expand_memory_with_personas, load_memory_corpus

        cases = load_memory_corpus()[:3]
        expanded = expand_memory_with_personas(cases, [], styles=_TEST_STYLE)
        assert expanded == []


# ---------------------------------------------------------------------------
# upsert_memory_test_cases tests
# ---------------------------------------------------------------------------


class TestUpsertMemoryTestCases:
    def _make_conn(self) -> sqlite3.Connection:
        """Create an in-memory SQLite DB with the memory_test_cases table."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            CREATE TABLE memory_test_cases (
                id                         INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id                    TEXT NOT NULL UNIQUE,
                category                   TEXT NOT NULL,
                memory_type                TEXT,
                variant                    TEXT NOT NULL,
                user_message               TEXT NOT NULL,
                cairn_response             TEXT NOT NULL,
                expected_detection         TEXT NOT NULL,
                expected_type              TEXT,
                expected_act_hint          TEXT,
                narrative_required_phrases TEXT,
                notes                      TEXT
            )
            """
        )
        conn.commit()
        return conn

    def test_inserts_all_cases(self) -> None:
        """upsert writes all cases to the DB."""
        from benchmarks.memory_corpus import load_memory_corpus, upsert_memory_test_cases

        conn = self._make_conn()
        cases = load_memory_corpus()
        count = upsert_memory_test_cases(conn, cases)
        assert count == 42
        row = conn.execute("SELECT COUNT(*) FROM memory_test_cases").fetchone()
        assert row[0] == 42

    def test_idempotent_upsert(self) -> None:
        """Calling upsert twice does not duplicate rows."""
        from benchmarks.memory_corpus import load_memory_corpus, upsert_memory_test_cases

        conn = self._make_conn()
        cases = load_memory_corpus()
        upsert_memory_test_cases(conn, cases)
        upsert_memory_test_cases(conn, cases)
        row = conn.execute("SELECT COUNT(*) FROM memory_test_cases").fetchone()
        assert row[0] == 42


# ---------------------------------------------------------------------------
# score_detection tests
# ---------------------------------------------------------------------------


class TestScoreDetection:
    def test_create_matches_create(self) -> None:
        from benchmarks.memory_matching import score_detection

        assert score_detection("CREATE", "CREATE") == 1

    def test_no_change_matches_no_change(self) -> None:
        from benchmarks.memory_matching import score_detection

        assert score_detection("NO_CHANGE", "NO_CHANGE") == 1

    def test_create_vs_no_change_is_zero(self) -> None:
        from benchmarks.memory_matching import score_detection

        assert score_detection("CREATE", "NO_CHANGE") == 0

    def test_none_actual_is_zero(self) -> None:
        from benchmarks.memory_matching import score_detection

        assert score_detection(None, "CREATE") == 0

    def test_none_actual_no_change_is_zero(self) -> None:
        from benchmarks.memory_matching import score_detection

        assert score_detection(None, "NO_CHANGE") == 0


# ---------------------------------------------------------------------------
# score_type tests
# ---------------------------------------------------------------------------


class TestScoreType:
    def test_expected_type_none_returns_none(self) -> None:
        """Negative cases have no expected type — return None."""
        from benchmarks.memory_matching import score_type

        assert score_type("fact", None, 1) is None

    def test_detection_wrong_returns_zero(self) -> None:
        """If detection failed, type score is 0 (not None)."""
        from benchmarks.memory_matching import score_type

        assert score_type("preference", "fact", 0) == 0

    def test_correct_type_returns_one(self) -> None:
        from benchmarks.memory_matching import score_type

        assert score_type("fact", "fact", 1) == 1

    def test_wrong_type_returns_zero(self) -> None:
        from benchmarks.memory_matching import score_type

        assert score_type("preference", "fact", 1) == 0

    def test_none_actual_type_returns_zero(self) -> None:
        """If pipeline produced no type but expected_type is set, score 0."""
        from benchmarks.memory_matching import score_type

        assert score_type(None, "commitment", 1) == 0

    def test_detection_wrong_overrides_correct_type(self) -> None:
        """Even if actual_type matches, detection_correct=0 gives 0."""
        from benchmarks.memory_matching import score_type

        assert score_type("fact", "fact", 0) == 0


# ---------------------------------------------------------------------------
# score_routing tests
# ---------------------------------------------------------------------------


class TestScoreRouting:
    def test_detection_wrong_returns_none(self) -> None:
        from benchmarks.memory_matching import score_routing

        assert score_routing("Career", "Career", 0) is None

    def test_no_hint_returns_none(self) -> None:
        from benchmarks.memory_matching import score_routing

        assert score_routing("Career", None, 1) is None

    def test_hint_found_case_insensitive(self) -> None:
        from benchmarks.memory_matching import score_routing

        assert score_routing("My Career Act", "career", 1) == 1

    def test_hint_not_found(self) -> None:
        from benchmarks.memory_matching import score_routing

        assert score_routing("Health & Wellness", "Career", 1) == 0

    def test_none_act_title_returns_zero(self) -> None:
        from benchmarks.memory_matching import score_routing

        assert score_routing(None, "Career", 1) == 0

    def test_exact_case_match(self) -> None:
        from benchmarks.memory_matching import score_routing

        assert score_routing("Career", "Career", 1) == 1


# ---------------------------------------------------------------------------
# score_narrative tests
# ---------------------------------------------------------------------------


class TestScoreNarrative:
    def test_detection_wrong_returns_none(self) -> None:
        from benchmarks.memory_matching import score_narrative

        assert score_narrative("Dataflow Systems", ["Dataflow"], 0) is None

    def test_empty_required_phrases_returns_none(self) -> None:
        from benchmarks.memory_matching import score_narrative

        assert score_narrative("some narrative", [], 1) is None

    def test_all_phrases_present(self) -> None:
        from benchmarks.memory_matching import score_narrative

        narrative = "Works at Dataflow as data engineer"
        assert score_narrative(narrative, ["Dataflow", "data engineer"], 1) == 1

    def test_missing_phrase_returns_zero(self) -> None:
        from benchmarks.memory_matching import score_narrative

        assert score_narrative("Works at Dataflow", ["Dataflow", "data engineer"], 1) == 0

    def test_case_insensitive_matching(self) -> None:
        from benchmarks.memory_matching import score_narrative

        assert score_narrative("DATAFLOW SYSTEMS senior", ["dataflow systems", "Senior"], 1) == 1

    def test_none_narrative_returns_zero(self) -> None:
        from benchmarks.memory_matching import score_narrative

        assert score_narrative(None, ["Dataflow"], 1) == 0

    def test_single_phrase_present(self) -> None:
        from benchmarks.memory_matching import score_narrative

        assert score_narrative("Marcus always has opinions", ["Marcus"], 1) == 1


# ---------------------------------------------------------------------------
# score_auto_approve tests
# ---------------------------------------------------------------------------


class TestScoreAutoApprove:
    def test_no_change_expected_returns_none(self) -> None:
        """Negative cases never reach the gate."""
        from benchmarks.memory_matching import score_auto_approve

        assert score_auto_approve("fact", "approved", "NO_CHANGE") is None

    def test_none_detected_type_returns_none(self) -> None:
        from benchmarks.memory_matching import score_auto_approve

        assert score_auto_approve(None, "approved", "CREATE") is None

    def test_none_memory_status_returns_none(self) -> None:
        from benchmarks.memory_matching import score_auto_approve

        assert score_auto_approve("fact", None, "CREATE") is None

    def test_fact_approved_returns_one(self) -> None:
        from benchmarks.memory_matching import score_auto_approve

        assert score_auto_approve("fact", "approved", "CREATE") == 1

    def test_preference_approved_returns_one(self) -> None:
        from benchmarks.memory_matching import score_auto_approve

        assert score_auto_approve("preference", "approved", "CREATE") == 1

    def test_relationship_approved_returns_one(self) -> None:
        from benchmarks.memory_matching import score_auto_approve

        assert score_auto_approve("relationship", "approved", "CREATE") == 1

    def test_fact_pending_returns_zero(self) -> None:
        """fact should be auto-approved; pending_review means gate failed."""
        from benchmarks.memory_matching import score_auto_approve

        assert score_auto_approve("fact", "pending_review", "CREATE") == 0

    def test_commitment_pending_review_returns_one(self) -> None:
        from benchmarks.memory_matching import score_auto_approve

        assert score_auto_approve("commitment", "pending_review", "CREATE") == 1

    def test_priority_pending_review_returns_one(self) -> None:
        from benchmarks.memory_matching import score_auto_approve

        assert score_auto_approve("priority", "pending_review", "CREATE") == 1

    def test_commitment_approved_returns_zero(self) -> None:
        """commitment should stay pending_review; approved means gate skipped it."""
        from benchmarks.memory_matching import score_auto_approve

        assert score_auto_approve("commitment", "approved", "CREATE") == 0

    def test_unknown_type_returns_none(self) -> None:
        """An unrecognised detected_type cannot be evaluated."""
        from benchmarks.memory_matching import score_auto_approve

        assert score_auto_approve("unknown_type", "approved", "CREATE") is None
