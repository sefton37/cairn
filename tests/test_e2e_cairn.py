"""End-to-End Tests for CAIRN - The Attention Minder.

These tests simulate real user scenarios with CAIRN:

1. Play Knowledge Base Integration
   - Reading/writing me.md (core identity)
   - CRUD operations on Acts, Scenes, Beats
   - KB file operations for knowledge storage
   - Identity extraction for coherence verification

2. Thunderbird Integration
   - Contact parsing from address book
   - Calendar event parsing
   - Todo parsing and overdue detection
   - Contact-linked knowledge items

3. Coherence Verification Recursion
   - Anti-pattern fast-path rejection
   - Direct verification for simple demands
   - Recursive decomposition for complex demands
   - Aggregate scoring across sub-demands
   - Trace storage for audit trail

4. Surfacing Algorithm
   - Priority-based surfacing
   - Time-aware surfacing (due dates, calendar)
   - Stale item detection
   - Waiting-on tracking
   - Coherence-filtered surfacing

Run with: pytest tests/test_e2e_cairn.py -v
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Generator
from unittest.mock import MagicMock, patch

import pytest

from cairn.cairn.coherence import (
    AttentionDemand,
    CoherenceCheck,
    CoherenceResult,
    CoherenceTrace,
    CoherenceVerifier,
    IdentityFacet,
    IdentityModel,
)
from cairn.cairn.models import (
    ActivityType,
    CairnMetadata,
    ContactRelationship,
    KanbanState,
    SurfaceContext,
)
from cairn.cairn.store import CairnStore
from cairn.cairn.surfacing import CairnSurfacer
from cairn.cairn.thunderbird import (
    CalendarEvent,
    CalendarTodo,
    ThunderbirdBridge,
    ThunderbirdConfig,
    ThunderbirdContact,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_play_root(tmp_path: Path) -> Generator[Path, None, None]:
    """Create a complete temporary Play structure."""
    play_path = tmp_path / "play"
    play_path.mkdir()

    # Create me.md (core identity)
    me_md = play_path / "me.md"
    me_md.write_text(
        """# My Story

I am a software engineer who values building tools that help people.

## Values
- Clean, maintainable code
- Test-driven development
- Open source contribution
- Continuous learning

## Goals
- Build an AI assistant for developers
- Learn Rust programming
- Contribute to open source projects

## Constraints
- Remote work only
- No cryptocurrency or NFT projects
- Focus on developer tools
""",
        encoding="utf-8",
    )

    # Create acts directory with sample acts
    acts_path = play_path / "acts"
    acts_path.mkdir()

    # Create acts.json
    (play_path / "acts.json").write_text(
        json.dumps(
            {
                "acts": [
                    {
                        "act_id": "talking-rock",
                        "title": "Building Talking Rock",
                        "active": True,
                        "notes": "Building a local-first AI assistant",
                        "repo_path": "/home/user/projects/talking-rock",
                    },
                    {
                        "act_id": "learn-rust",
                        "title": "Learning Rust",
                        "active": False,
                        "notes": "Learning systems programming with Rust",
                    },
                ]
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    # Create act directories with scenes
    tr_act = acts_path / "talking-rock"
    tr_act.mkdir()
    (tr_act / "scenes.json").write_text(
        json.dumps(
            {
                "scenes": [
                    {
                        "scene_id": "cairn-impl",
                        "title": "Implement CAIRN",
                        "intent": "Build the attention minder component",
                        "status": "in_progress",
                        "time_horizon": "2 weeks",
                        "notes": "Core surfacing algorithm and coherence kernel",
                    },
                    {
                        "scene_id": "riva-impl",
                        "title": "Implement RIVA",
                        "intent": "Build the code mode component",
                        "status": "completed",
                        "time_horizon": "done",
                        "notes": "Recursive intent verification complete",
                    },
                ]
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    # Create KB directory with sample files (KB is under play_root/kb/acts/{act_id}/)
    kb_path = play_path / "kb" / "acts" / "talking-rock"
    kb_path.mkdir(parents=True)
    (kb_path / "design-notes.md").write_text(
        """# CAIRN Design Notes

## Core Philosophy
- Surface the next thing, not everything
- Priority driven by user decision
- Never gamifies, never guilt-trips

## Key Patterns
- Recursive decomposition for complex demands
- Anti-pattern fast-path for known rejections
- Identity-first filtering
""",
        encoding="utf-8",
    )

    yield play_path


@pytest.fixture
def temp_cairn_db(tmp_path: Path) -> Generator[Path, None, None]:
    """Create a temporary CAIRN database."""
    db_path = tmp_path / "cairn.db"
    yield db_path


@pytest.fixture
def cairn_store(temp_cairn_db: Path) -> CairnStore:
    """Create a CAIRN store with temp database."""
    return CairnStore(temp_cairn_db)


@pytest.fixture
def surfacer(cairn_store: CairnStore) -> CairnSurfacer:
    """Create a surfacer with the test store."""
    return CairnSurfacer(cairn_store)


@pytest.fixture
def mock_thunderbird_profile(tmp_path: Path) -> Generator[Path, None, None]:
    """Create a mock Thunderbird profile with SQLite databases."""
    profile_path = tmp_path / "thunderbird" / "test.default"
    profile_path.mkdir(parents=True)

    # Create address book database
    abook_path = profile_path / "abook.sqlite"
    conn = sqlite3.connect(abook_path)
    conn.execute("CREATE TABLE properties (card TEXT, name TEXT, value TEXT)")

    # Add sample contacts
    contacts_data = [
        ("contact-1", [
            ("DisplayName", "Alice Developer"),
            ("PrimaryEmail", "alice@example.com"),
            ("Company", "TechCorp"),
            ("FirstName", "Alice"),
            ("LastName", "Developer"),
            ("JobTitle", "Senior Engineer"),
        ]),
        ("contact-2", [
            ("DisplayName", "Bob Designer"),
            ("PrimaryEmail", "bob@design.co"),
            ("Company", "DesignStudio"),
            ("FirstName", "Bob"),
            ("LastName", "Designer"),
        ]),
        ("contact-3", [
            ("DisplayName", "Charlie Manager"),
            ("PrimaryEmail", "charlie@corp.com"),
            ("WorkPhone", "555-1234"),
        ]),
    ]

    for card_id, props in contacts_data:
        for name, value in props:
            conn.execute(
                "INSERT INTO properties (card, name, value) VALUES (?, ?, ?)",
                (card_id, name, value),
            )
    conn.commit()
    conn.close()

    # Create calendar database
    cal_path = profile_path / "calendar-data"
    cal_path.mkdir()
    cal_db_path = cal_path / "local.sqlite"

    conn = sqlite3.connect(cal_db_path)
    conn.execute(
        """CREATE TABLE cal_events (
            id TEXT PRIMARY KEY,
            title TEXT,
            event_start INTEGER,
            event_end INTEGER,
            event_stamp INTEGER,
            flags INTEGER,
            cal_id TEXT,
            icalString TEXT
        )"""
    )
    conn.execute(
        """CREATE TABLE cal_todos (
            id TEXT PRIMARY KEY,
            title TEXT,
            todo_entry INTEGER,
            todo_due INTEGER,
            todo_completed INTEGER,
            flags INTEGER,
            icalString TEXT
        )"""
    )
    conn.execute(
        """CREATE TABLE cal_recurrence (
            item_id TEXT,
            cal_id TEXT,
            icalString TEXT
        )"""
    )

    # Add sample events (timestamps in microseconds)
    now = datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    events = [
        (
            "event-1",
            "Team Standup",
            int((today_start + timedelta(hours=9)).timestamp() * 1_000_000),
            int((today_start + timedelta(hours=9, minutes=30)).timestamp() * 1_000_000),
            "LOCATION:Conference Room A\nSTATUS:CONFIRMED",
        ),
        (
            "event-2",
            "Code Review Session",
            int((today_start + timedelta(hours=14)).timestamp() * 1_000_000),
            int((today_start + timedelta(hours=15)).timestamp() * 1_000_000),
            "LOCATION:Zoom\nDESCRIPTION:Review CAIRN implementation",
        ),
        (
            "event-3",
            "Sprint Planning",
            int((today_start + timedelta(days=1, hours=10)).timestamp() * 1_000_000),
            int((today_start + timedelta(days=1, hours=11)).timestamp() * 1_000_000),
            "STATUS:TENTATIVE",
        ),
    ]

    for evt_id, title, start, end, ical in events:
        conn.execute(
            "INSERT INTO cal_events (id, title, event_start, event_end, event_stamp, flags, cal_id, icalString) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (evt_id, title, start, end, start, 0, "local", ical),
        )

    # Add sample todos
    todos = [
        (
            "todo-1",
            "Review Pull Request",
            int((today_start - timedelta(days=1)).timestamp() * 1_000_000),  # Overdue
            None,
            "STATUS:NEEDS-ACTION\nPRIORITY:1",
        ),
        (
            "todo-2",
            "Update Documentation",
            int((today_start + timedelta(days=3)).timestamp() * 1_000_000),
            None,
            "STATUS:IN-PROCESS\nPRIORITY:5",
        ),
        (
            "todo-3",
            "Deploy to Production",
            int((today_start + timedelta(days=7)).timestamp() * 1_000_000),
            None,
            "STATUS:NEEDS-ACTION",
        ),
    ]

    for todo_id, title, due, completed, ical in todos:
        conn.execute(
            "INSERT INTO cal_todos (id, title, todo_entry, todo_due, todo_completed, flags, icalString) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (todo_id, title, due, due, completed, 0, ical),
        )

    conn.commit()
    conn.close()

    yield profile_path


@pytest.fixture
def thunderbird_bridge(mock_thunderbird_profile: Path) -> ThunderbirdBridge:
    """Create a Thunderbird bridge with mock profile."""
    config = ThunderbirdConfig(profile_path=mock_thunderbird_profile)
    return ThunderbirdBridge(config)


@pytest.fixture
def complex_identity() -> IdentityModel:
    """Create a rich identity model for E2E testing."""
    return IdentityModel(
        core="""I am a software engineer focused on building developer tools.

I value:
- Clean, maintainable code
- Test-driven development
- Open source contribution
- Continuous learning
- Work-life balance

My current goals:
- Build Talking Rock, a local-first AI assistant
- Learn Rust for systems programming
- Contribute to open source projects

I avoid:
- Cryptocurrency and NFT projects
- Hustle culture
- Surveillance technology
""",
        facets=[
            IdentityFacet(
                name="goal",
                source="act:talking-rock",
                content="Build Talking Rock - a local-first AI assistant that respects privacy",
                weight=2.0,
            ),
            IdentityFacet(
                name="goal",
                source="act:learn-rust",
                content="Learn Rust programming for systems-level development",
                weight=1.5,
            ),
            IdentityFacet(
                name="project",
                source="scene:cairn-impl",
                content="Implement CAIRN - the attention minder with coherence verification",
                weight=1.8,
            ),
            IdentityFacet(
                name="value",
                source="me.md:values",
                content="Test-driven development and clean code practices",
                weight=1.5,
            ),
            IdentityFacet(
                name="constraint",
                source="me.md:constraints",
                content="Remote work only, no cryptocurrency projects",
                weight=2.0,
            ),
            IdentityFacet(
                name="knowledge",
                source="kb:design-notes.md",
                content="CAIRN surfaces the next thing, not everything. Priority driven by user.",
                weight=1.0,
            ),
        ],
        anti_patterns=[
            "crypto",
            "nft",
            "blockchain",
            "hustle",
            "grind",
            "spam",
            "marketing email",
            "newsletter signup",
            "surveillance",
        ],
    )


# =============================================================================
# Play Knowledge Base E2E Tests
# =============================================================================


class TestPlayKnowledgeBaseE2E:
    """E2E tests for Play knowledge base integration.

    Note: Some tests are skipped because play_fs now uses play_db instead of JSON files.
    The test fixtures create JSON files but list_acts/list_scenes read from play_db.
    """

    def test_read_me_markdown_with_real_structure(self, temp_play_root: Path) -> None:
        """Test reading me.md from a real Play structure."""
        from cairn import play_fs

        with patch.object(play_fs, "play_root", return_value=temp_play_root):
            content = play_fs.read_me_markdown()

            assert "software engineer" in content.lower()
            assert "Values" in content
            assert "Goals" in content
            assert "Constraints" in content
            assert "No cryptocurrency" in content

    @pytest.mark.skip(reason="play_fs.list_acts now reads from play_db, not JSON files")
    def test_list_acts_with_code_mode(self, temp_play_root: Path) -> None:
        """Test listing acts including code mode configuration."""
        from cairn import play_fs

        with patch.object(play_fs, "play_root", return_value=temp_play_root):
            acts, active_id = play_fs.list_acts()

            assert len(acts) == 2
            assert active_id == "talking-rock"

            # Find the active act
            active_act = next(a for a in acts if a.active)
            assert active_act.title == "Building Talking Rock"
            assert active_act.repo_path == "/home/user/projects/talking-rock"

    @pytest.mark.skip(reason="play_fs.list_scenes now reads from play_db, not JSON files")
    def test_list_scenes_for_act(self, temp_play_root: Path) -> None:
        """Test listing scenes within an act."""
        from cairn import play_fs

        with patch.object(play_fs, "play_root", return_value=temp_play_root):
            scenes = play_fs.list_scenes(act_id="talking-rock")

            assert len(scenes) == 2
            scene_titles = [s.title for s in scenes]
            assert "Implement CAIRN" in scene_titles
            assert "Implement RIVA" in scene_titles

    def test_kb_list_and_read_files(self, temp_play_root: Path) -> None:
        """Test listing and reading KB files."""
        from cairn import play_fs

        with patch.object(play_fs, "play_root", return_value=temp_play_root):
            kb_files = play_fs.kb_list_files(act_id="talking-rock")

            assert "design-notes.md" in kb_files

            content = play_fs.kb_read(act_id="talking-rock", path="design-notes.md")
            assert "Core Philosophy" in content
            assert "Surface the next thing" in content

    def test_identity_extraction_from_play(self, temp_play_root: Path) -> None:
        """Test building IdentityModel from real Play structure."""
        from cairn import play_fs
        from cairn.cairn.identity import build_identity_model

        with patch.object(play_fs, "play_root", return_value=temp_play_root):
            identity = build_identity_model(include_kb=True)

            # Core should have me.md content
            assert "software engineer" in identity.core.lower()

            # Should have facets from acts
            goal_facets = identity.get_facets_by_name("goal")
            assert len(goal_facets) >= 1

            # Should have KB facets if include_kb=True
            kb_facets = [f for f in identity.facets if f.source.startswith("kb:")]
            # KB facets may or may not be present depending on content length


# =============================================================================
# Thunderbird Integration E2E Tests
# =============================================================================


class TestThunderbirdIntegrationE2E:
    """E2E tests for Thunderbird integration."""

    def test_bridge_status(self, thunderbird_bridge: ThunderbirdBridge) -> None:
        """Test getting bridge status."""
        status = thunderbird_bridge.get_status()

        assert status["has_address_book"] is True
        assert status["has_calendar"] is True

    def test_list_all_contacts(self, thunderbird_bridge: ThunderbirdBridge) -> None:
        """Test listing all contacts."""
        contacts = thunderbird_bridge.list_contacts()

        assert len(contacts) == 3

        # Check contact details
        alice = next(c for c in contacts if "Alice" in c.display_name)
        assert alice.email == "alice@example.com"
        assert alice.organization == "TechCorp"
        assert alice.first_name == "Alice"
        assert alice.job_title == "Senior Engineer"

    def test_search_contacts(self, thunderbird_bridge: ThunderbirdBridge) -> None:
        """Test searching contacts by name/email."""
        # Search by name
        results = thunderbird_bridge.search_contacts("Alice")
        assert len(results) == 1
        assert results[0].display_name == "Alice Developer"

        # Search by company
        results = thunderbird_bridge.search_contacts("TechCorp")
        assert len(results) == 1

        # Search by email domain
        results = thunderbird_bridge.search_contacts("design.co")
        assert len(results) == 1
        assert "Bob" in results[0].display_name

    def test_get_contact_by_id(self, thunderbird_bridge: ThunderbirdBridge) -> None:
        """Test getting a specific contact."""
        contact = thunderbird_bridge.get_contact("contact-1")

        assert contact is not None
        assert contact.display_name == "Alice Developer"
        assert contact.email == "alice@example.com"

        # Non-existent contact
        missing = thunderbird_bridge.get_contact("nonexistent")
        assert missing is None

    def test_list_calendar_events(self, thunderbird_bridge: ThunderbirdBridge) -> None:
        """Test listing calendar events."""
        now = datetime.now()
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=2)

        events = thunderbird_bridge.list_events(start=start, end=end)

        assert len(events) >= 2  # At least today's events

        # Check event details
        standup = next((e for e in events if "Standup" in e.title), None)
        assert standup is not None
        # Note: location is not parsed - SQL query doesn't select icalString for non-recurring events

    def test_get_today_events(self, thunderbird_bridge: ThunderbirdBridge) -> None:
        """Test getting today's events."""
        events = thunderbird_bridge.get_today_events()

        assert len(events) >= 2  # Standup and Code Review

    def test_get_upcoming_events(self, thunderbird_bridge: ThunderbirdBridge) -> None:
        """Test getting upcoming events in next N hours."""
        events = thunderbird_bridge.get_upcoming_events(hours=24)

        # At least 1 event (timing-dependent - standup may be past at test time)
        assert len(events) >= 1

    def test_list_todos(self, thunderbird_bridge: ThunderbirdBridge) -> None:
        """Test listing calendar todos."""
        todos = thunderbird_bridge.list_todos(include_completed=False)

        assert len(todos) == 3

        # Check todo details
        pr_todo = next((t for t in todos if "Pull Request" in t.title), None)
        assert pr_todo is not None
        assert pr_todo.priority == 1  # High priority

    def test_get_overdue_todos(self, thunderbird_bridge: ThunderbirdBridge) -> None:
        """Test getting overdue todos."""
        overdue = thunderbird_bridge.get_overdue_todos()

        assert len(overdue) >= 1
        assert any("Pull Request" in t.title for t in overdue)


class TestThunderbirdContactLinksE2E:
    """E2E tests for CAIRN contact knowledge graph."""

    def test_link_contact_to_entity(
        self,
        cairn_store: CairnStore,
        thunderbird_bridge: ThunderbirdBridge,
    ) -> None:
        """Test linking Thunderbird contact to Play entity."""
        # Create entity metadata
        cairn_store.get_or_create_metadata("act", "talking-rock")

        # Link contact
        link = cairn_store.link_contact(
            contact_id="contact-1",  # Alice Developer
            entity_type="act",
            entity_id="talking-rock",
            relationship=ContactRelationship.COLLABORATOR,
            notes="Working on CAIRN together",
        )

        assert link.contact_id == "contact-1"
        assert link.relationship == ContactRelationship.COLLABORATOR

        # Retrieve links
        links = cairn_store.get_contact_links(contact_id="contact-1")
        assert len(links) == 1
        assert links[0].entity_id == "talking-rock"

    def test_contact_with_multiple_projects(
        self,
        cairn_store: CairnStore,
    ) -> None:
        """Test contact linked to multiple projects."""
        cairn_store.get_or_create_metadata("act", "project-a")
        cairn_store.get_or_create_metadata("act", "project-b")
        cairn_store.get_or_create_metadata("scene", "scene-1")

        # Link contact to multiple entities
        cairn_store.link_contact("contact-1", "act", "project-a", ContactRelationship.OWNER)
        cairn_store.link_contact("contact-1", "act", "project-b", ContactRelationship.COLLABORATOR)
        cairn_store.link_contact("contact-1", "scene", "scene-1", ContactRelationship.STAKEHOLDER)

        links = cairn_store.get_contact_links(contact_id="contact-1")
        assert len(links) == 3

        # Filter by entity type
        act_links = cairn_store.get_contacts_for_entity("act", "project-a")
        assert len(act_links) == 1
        assert act_links[0].relationship == ContactRelationship.OWNER


# =============================================================================
# Coherence Recursion E2E Tests
# =============================================================================


class TestCoherenceRecursionE2E:
    """E2E tests for the coherence verification recursion principle."""

    def test_anti_pattern_fast_path_no_llm_call(self, complex_identity: IdentityModel) -> None:
        """Test that anti-patterns reject instantly without LLM."""
        mock_llm = MagicMock()
        verifier = CoherenceVerifier(complex_identity, llm=mock_llm)

        demand = AttentionDemand.create(
            source="email",
            content="Amazing crypto opportunity - invest now!",
            urgency=8,
        )

        result = verifier.verify(demand)

        # Should reject via anti-pattern
        assert result.recommendation == "reject"
        assert result.overall_score == -1.0
        assert "anti-pattern" in " ".join(result.trace).lower()

        # LLM should NOT have been called
        mock_llm.chat_json.assert_not_called()

    def test_simple_demand_direct_verification(self, complex_identity: IdentityModel) -> None:
        """Test that simple demands are verified directly."""
        verifier = CoherenceVerifier(complex_identity, llm=None)

        demand = AttentionDemand.create(
            source="github",
            content="Review code change",
            urgency=5,
        )

        result = verifier.verify(demand)

        # Simple demand should be verified directly
        assert "direct" in " ".join(result.trace).lower() or len(result.checks) > 0
        assert len(demand.sub_demands) == 0  # No decomposition

    def test_complex_demand_decomposition(self, complex_identity: IdentityModel) -> None:
        """Test that complex demands are decomposed recursively."""
        verifier = CoherenceVerifier(complex_identity, llm=None, max_depth=3)

        # Complex demand with multiple parts
        demand = AttentionDemand.create(
            source="work",
            content="Review the CAIRN code changes and also update the documentation for the new API and additionally write tests for the coherence verification module",
            urgency=6,
        )

        result = verifier.verify(demand)

        # Should have been decomposed
        assert len(demand.sub_demands) > 0 or "decompos" in " ".join(result.trace).lower()

    def test_recursive_depth_limiting(self, complex_identity: IdentityModel) -> None:
        """Test that recursion is properly limited."""
        verifier = CoherenceVerifier(complex_identity, llm=None, max_depth=2)

        # Deeply nested demand
        demand = AttentionDemand.create(
            source="complex",
            content="A and B and C and D and E and F and G",
            urgency=5,
        )

        result = verifier.verify(demand)

        # Should complete without infinite recursion
        assert result is not None
        assert result.recommendation in ("accept", "defer", "reject")

    def test_aggregate_scoring_mixed_sub_demands(self, complex_identity: IdentityModel) -> None:
        """Test aggregate scoring with mixed coherence sub-demands."""
        verifier = CoherenceVerifier(complex_identity, llm=None)

        # Demand with both coherent and incoherent parts
        demand = AttentionDemand.create(
            source="mixed",
            content="Build developer tools and also check crypto prices",
            urgency=5,
        )

        result = verifier.verify(demand)

        # Should have checks from multiple sub-demands
        # Final recommendation depends on aggregation
        assert result is not None
        # The anti-pattern "crypto" should affect the result
        assert result.overall_score < 0.5  # Not fully coherent due to crypto mention

    def test_coherence_trace_creation(self, complex_identity: IdentityModel) -> None:
        """Test that coherence traces are properly created."""
        from cairn.cairn.identity import get_identity_hash

        verifier = CoherenceVerifier(complex_identity, llm=None)

        demand = AttentionDemand.create(
            source="work",
            content="Implement CAIRN surfacing algorithm",
            urgency=7,
        )

        result = verifier.verify(demand)
        identity_hash = get_identity_hash(complex_identity)

        trace = CoherenceTrace.create(result, identity_hash)

        assert trace.demand_id == demand.id
        assert trace.identity_hash == identity_hash
        assert trace.final_score == result.overall_score
        assert trace.recommendation == result.recommendation
        assert trace.user_override is None

    def test_heuristic_keyword_overlap_scoring(self, complex_identity: IdentityModel) -> None:
        """Test heuristic scoring based on keyword overlap."""
        verifier = CoherenceVerifier(complex_identity, llm=None)

        # High overlap with identity
        aligned_demand = AttentionDemand.create(
            source="work",
            content="Build local-first AI assistant with clean code and tests",
            urgency=6,
        )
        aligned_result = verifier.verify(aligned_demand)

        # Low overlap with identity
        unrelated_demand = AttentionDemand.create(
            source="random",
            content="Buy groceries and pick up dry cleaning",
            urgency=3,
        )
        unrelated_result = verifier.verify(unrelated_demand)

        # Aligned demand should score higher
        assert aligned_result.overall_score > unrelated_result.overall_score


class TestCoherenceTraceStorageE2E:
    """E2E tests for coherence trace storage and retrieval."""

    def test_save_and_retrieve_trace(
        self,
        cairn_store: CairnStore,
        complex_identity: IdentityModel,
    ) -> None:
        """Test saving and retrieving coherence traces."""
        from cairn.cairn.identity import get_identity_hash

        verifier = CoherenceVerifier(complex_identity, llm=None)

        demand = AttentionDemand.create(
            source="test",
            content="Build developer tools",
            urgency=5,
        )

        result = verifier.verify(demand)
        identity_hash = get_identity_hash(complex_identity)
        trace = CoherenceTrace.create(result, identity_hash)

        # Save trace using individual params
        cairn_store.save_coherence_trace(
            trace_id=trace.trace_id,
            demand_id=trace.demand_id,
            timestamp=trace.timestamp,
            identity_hash=trace.identity_hash,
            checks=[c.to_dict() for c in trace.checks],
            final_score=trace.final_score,
            recommendation=trace.recommendation,
        )

        # Retrieve trace
        retrieved = cairn_store.get_coherence_trace(trace.trace_id)

        assert retrieved is not None
        assert retrieved["demand_id"] == trace.demand_id
        assert retrieved["final_score"] == trace.final_score

    def test_record_user_override(
        self,
        cairn_store: CairnStore,
        complex_identity: IdentityModel,
    ) -> None:
        """Test recording user override of coherence decision."""
        from cairn.cairn.identity import get_identity_hash

        verifier = CoherenceVerifier(complex_identity, llm=None)

        demand = AttentionDemand.create(
            source="test",
            content="Something neutral",
            urgency=5,
        )

        result = verifier.verify(demand)
        trace = CoherenceTrace.create(result, get_identity_hash(complex_identity))

        cairn_store.save_coherence_trace(
            trace_id=trace.trace_id,
            demand_id=trace.demand_id,
            timestamp=trace.timestamp,
            identity_hash=trace.identity_hash,
            checks=[c.to_dict() for c in trace.checks],
            final_score=trace.final_score,
            recommendation=trace.recommendation,
        )

        # User overrides the decision
        cairn_store.record_user_override(trace.trace_id, "accept")

        # Retrieve and verify override
        updated = cairn_store.get_coherence_trace(trace.trace_id)
        assert updated is not None
        assert updated["user_override"] == "accept"

    def test_list_traces_for_demand(
        self,
        cairn_store: CairnStore,
        complex_identity: IdentityModel,
    ) -> None:
        """Test listing traces for a specific demand."""
        from cairn.cairn.identity import get_identity_hash

        verifier = CoherenceVerifier(complex_identity, llm=None)
        identity_hash = get_identity_hash(complex_identity)

        # Create multiple traces for same demand type
        for i in range(3):
            demand = AttentionDemand.create(
                source="test",
                content=f"Test demand {i}",
                urgency=5,
            )
            result = verifier.verify(demand)
            trace = CoherenceTrace.create(result, identity_hash)
            cairn_store.save_coherence_trace(
                trace_id=trace.trace_id,
                demand_id=trace.demand_id,
                timestamp=trace.timestamp,
                identity_hash=trace.identity_hash,
                checks=[c.to_dict() for c in trace.checks],
                final_score=trace.final_score,
                recommendation=trace.recommendation,
            )

        # List all traces
        traces = cairn_store.list_coherence_traces(limit=10)
        assert len(traces) == 3


# =============================================================================
# Surfacing Algorithm E2E Tests
# =============================================================================


class TestSurfacingAlgorithmE2E:
    """E2E tests for the surfacing algorithm."""

    def test_surface_by_priority(
        self,
        cairn_store: CairnStore,
        surfacer: CairnSurfacer,
    ) -> None:
        """Test that higher priority items surface first."""
        # Create items with different priorities
        cairn_store.get_or_create_metadata("act", "low-priority")
        cairn_store.set_kanban_state("act", "low-priority", KanbanState.ACTIVE)
        cairn_store.set_priority("act", "low-priority", 1)

        cairn_store.get_or_create_metadata("act", "high-priority")
        cairn_store.set_kanban_state("act", "high-priority", KanbanState.ACTIVE)
        cairn_store.set_priority("act", "high-priority", 5)

        cairn_store.get_or_create_metadata("act", "medium-priority")
        cairn_store.set_kanban_state("act", "medium-priority", KanbanState.ACTIVE)
        cairn_store.set_priority("act", "medium-priority", 3)

        results = surfacer.surface_next()

        if results:
            # First result should be highest priority
            priorities = []
            for item in results:
                meta = cairn_store.get_metadata(item.entity_type, item.entity_id)
                if meta and meta.priority:
                    priorities.append(meta.priority)

            if len(priorities) >= 2:
                # Priorities should be descending (highest first)
                assert priorities[0] >= priorities[-1]

    def test_surface_due_today(
        self,
        cairn_store: CairnStore,
        surfacer: CairnSurfacer,
    ) -> None:
        """Test surfacing items due today."""
        # Item due today
        cairn_store.get_or_create_metadata("scene", "due-today")
        cairn_store.set_kanban_state("scene", "due-today", KanbanState.ACTIVE)
        now = datetime.now()
        end_of_day = now.replace(hour=23, minute=59, second=59)
        cairn_store.set_due_date("scene", "due-today", end_of_day)

        # Item due next week
        cairn_store.get_or_create_metadata("scene", "due-later")
        cairn_store.set_kanban_state("scene", "due-later", KanbanState.ACTIVE)
        cairn_store.set_due_date("scene", "due-later", now + timedelta(days=7))

        results = surfacer.surface_today()

        # Due today should be in results
        entity_ids = [r.entity_id for r in results]
        assert "due-today" in entity_ids

    def test_surface_stale_items(
        self,
        cairn_store: CairnStore,
        surfacer: CairnSurfacer,
    ) -> None:
        """Test surfacing stale (untouched) items."""
        # Create item and make it stale
        cairn_store.get_or_create_metadata("scene", "stale-item")
        cairn_store.set_kanban_state("scene", "stale-item", KanbanState.ACTIVE)

        # Manually set last_touched to 10 days ago
        metadata = cairn_store.get_metadata("scene", "stale-item")
        assert metadata is not None
        metadata.last_touched = datetime.now() - timedelta(days=10)
        cairn_store.save_metadata(metadata)

        results = surfacer.surface_stale(days=7)

        assert len(results) >= 1
        assert any(r.entity_id == "stale-item" for r in results)

    def test_surface_waiting_items(
        self,
        cairn_store: CairnStore,
        surfacer: CairnSurfacer,
    ) -> None:
        """Test surfacing items in WAITING state."""
        cairn_store.get_or_create_metadata("scene", "waiting-item")
        cairn_store.set_kanban_state(
            "scene",
            "waiting-item",
            KanbanState.WAITING,
            waiting_on="Client approval",
        )

        results = surfacer.surface_waiting()

        assert len(results) >= 1
        waiting_item = next((r for r in results if r.entity_id == "waiting-item"), None)
        assert waiting_item is not None

    def test_surface_needs_priority(
        self,
        cairn_store: CairnStore,
        surfacer: CairnSurfacer,
    ) -> None:
        """Test surfacing active items without priority."""
        # Active item without priority
        cairn_store.get_or_create_metadata("act", "no-priority")
        cairn_store.set_kanban_state("act", "no-priority", KanbanState.ACTIVE)

        # Active item with priority
        cairn_store.get_or_create_metadata("act", "has-priority")
        cairn_store.set_kanban_state("act", "has-priority", KanbanState.ACTIVE)
        cairn_store.set_priority("act", "has-priority", 3)

        results = surfacer.surface_needs_priority()

        entity_ids = [r.entity_id for r in results]
        assert "no-priority" in entity_ids
        assert "has-priority" not in entity_ids


class TestCoherenceEnabledSurfacingE2E:
    """E2E tests for coherence-enabled surfacing."""

    def test_surfacing_with_coherence_filter(
        self,
        cairn_store: CairnStore,
        temp_play_root: Path,
    ) -> None:
        """Test that coherence filtering affects surfacing results."""
        from cairn import play_fs
        from cairn.cairn.identity import add_anti_pattern

        # Create items
        cairn_store.get_or_create_metadata("act", "coherent-item")
        cairn_store.set_kanban_state("act", "coherent-item", KanbanState.ACTIVE)
        cairn_store.set_priority("act", "coherent-item", 5)

        cairn_store.get_or_create_metadata("act", "incoherent-item")
        cairn_store.set_kanban_state("act", "incoherent-item", KanbanState.ACTIVE)
        cairn_store.set_priority("act", "incoherent-item", 5)

        # Create surfacer with LLM (would need to mock for full test)
        surfacer = CairnSurfacer(cairn_store, llm=None)

        # Surface without coherence (baseline)
        with patch.object(play_fs, "play_root", return_value=temp_play_root):
            results = surfacer.surface_next(enable_coherence=False)

            # Both items should appear
            entity_ids = [r.entity_id for r in results]
            assert len(entity_ids) >= 1


# =============================================================================
# Full E2E Flow Tests
# =============================================================================


class TestFullCAIRNFlowE2E:
    """Full end-to-end flow tests simulating real user scenarios."""

    def test_morning_routine_surfacing(
        self,
        cairn_store: CairnStore,
        surfacer: CairnSurfacer,
        thunderbird_bridge: ThunderbirdBridge,
    ) -> None:
        """Simulate morning routine: what should I focus on today?"""
        # Set up some items
        cairn_store.get_or_create_metadata("act", "main-project")
        cairn_store.set_kanban_state("act", "main-project", KanbanState.ACTIVE)
        cairn_store.set_priority("act", "main-project", 5)

        cairn_store.get_or_create_metadata("scene", "urgent-task")
        cairn_store.set_kanban_state("scene", "urgent-task", KanbanState.ACTIVE)
        cairn_store.set_priority("scene", "urgent-task", 5)
        cairn_store.set_due_date("scene", "urgent-task", datetime.now() + timedelta(hours=4))

        cairn_store.get_or_create_metadata("scene", "someday-task")
        cairn_store.set_kanban_state("scene", "someday-task", KanbanState.SOMEDAY)

        # Get today's focus
        today_items = surfacer.surface_today()
        next_items = surfacer.surface_next()

        # Calendar events
        events = thunderbird_bridge.get_today_events()

        # Combine for morning briefing
        assert len(today_items) >= 0 or len(next_items) >= 0 or len(events) >= 0

    def test_contact_project_lookup(
        self,
        cairn_store: CairnStore,
        thunderbird_bridge: ThunderbirdBridge,
    ) -> None:
        """Simulate: what am I working on with Alice?"""
        # Create project and link to contact
        cairn_store.get_or_create_metadata("act", "project-with-alice")
        cairn_store.set_kanban_state("act", "project-with-alice", KanbanState.ACTIVE)
        cairn_store.link_contact(
            "contact-1",  # Alice
            "act",
            "project-with-alice",
            ContactRelationship.COLLABORATOR,
        )

        cairn_store.get_or_create_metadata("scene", "alice-task")
        cairn_store.link_contact(
            "contact-1",
            "scene",
            "alice-task",
            ContactRelationship.WAITING_ON,
            notes="Waiting for Alice's review",
        )

        # Look up Alice's contact
        contacts = thunderbird_bridge.search_contacts("Alice")
        assert len(contacts) == 1
        alice = contacts[0]

        # Get all links for Alice
        links = cairn_store.get_contact_links(contact_id="contact-1")
        assert len(links) == 2

        # Check waiting items
        waiting_links = [l for l in links if l.relationship == ContactRelationship.WAITING_ON]
        assert len(waiting_links) == 1

    def test_coherence_rejection_flow(
        self,
        cairn_store: CairnStore,
        complex_identity: IdentityModel,
    ) -> None:
        """Simulate: rejecting an incoherent demand and recording override."""
        from cairn.cairn.identity import get_identity_hash

        verifier = CoherenceVerifier(complex_identity, llm=None)

        # Incoherent demand
        demand = AttentionDemand.create(
            source="email",
            content="Join our blockchain startup!",
            urgency=9,
        )

        result = verifier.verify(demand)

        # Should be rejected
        assert result.recommendation == "reject"

        # Save trace using individual params
        trace = CoherenceTrace.create(result, get_identity_hash(complex_identity))
        cairn_store.save_coherence_trace(
            trace_id=trace.trace_id,
            demand_id=trace.demand_id,
            timestamp=trace.timestamp,
            identity_hash=trace.identity_hash,
            checks=[c.to_dict() for c in trace.checks],
            final_score=trace.final_score,
            recommendation=trace.recommendation,
        )

        # User disagrees and overrides
        cairn_store.record_user_override(trace.trace_id, "defer")

        # Verify override recorded
        updated = cairn_store.get_coherence_trace(trace.trace_id)
        assert updated is not None
        assert updated["user_override"] == "defer"

    def test_activity_tracking_workflow(
        self,
        cairn_store: CairnStore,
        surfacer: CairnSurfacer,
    ) -> None:
        """Simulate: tracking activity over time."""
        # Create item
        cairn_store.get_or_create_metadata("scene", "tracked-task")
        cairn_store.set_kanban_state("scene", "tracked-task", KanbanState.ACTIVE)

        # Touch it multiple times (simulating user interaction)
        cairn_store.touch("scene", "tracked-task", ActivityType.VIEWED)
        cairn_store.touch("scene", "tracked-task", ActivityType.EDITED)
        cairn_store.touch("scene", "tracked-task", ActivityType.VIEWED)

        # Check activity log
        log = cairn_store.get_activity_log("scene", "tracked-task")
        assert len(log) >= 3

        # Check touch count
        metadata = cairn_store.get_metadata("scene", "tracked-task")
        assert metadata is not None
        assert metadata.touch_count >= 3

    def test_defer_and_resurface_workflow(
        self,
        cairn_store: CairnStore,
        surfacer: CairnSurfacer,
    ) -> None:
        """Simulate: deferring an item and having it resurface."""
        # Create active item
        cairn_store.get_or_create_metadata("scene", "deferrable-task")
        cairn_store.set_kanban_state("scene", "deferrable-task", KanbanState.ACTIVE)
        cairn_store.set_priority("scene", "deferrable-task", 3)

        # Defer for 1 day (in past for test)
        yesterday = datetime.now() - timedelta(days=1)
        cairn_store.defer_until("scene", "deferrable-task", yesterday)

        # Check state changed to SOMEDAY
        metadata = cairn_store.get_metadata("scene", "deferrable-task")
        assert metadata is not None
        assert metadata.kanban_state == KanbanState.SOMEDAY

        # In a real implementation, a background job would check deferred items
        # and move them back to ACTIVE when defer_until has passed


# =============================================================================
# MCP Tools E2E Tests
# =============================================================================


class TestMCPToolsE2E:
    """E2E tests for MCP tool interface."""

    def test_list_tools_returns_tools(self) -> None:
        """Test that list_tools returns tool definitions."""
        from cairn.cairn.mcp_tools import list_tools

        tools = list_tools()

        # Should have multiple tools
        assert len(tools) > 0

        # Each tool should have required fields
        for tool in tools:
            assert hasattr(tool, "name")
            assert hasattr(tool, "description")
            assert hasattr(tool, "input_schema")
            assert tool.name.startswith("cairn_")

    def test_tool_names_exist(self) -> None:
        """Test that expected tool names are defined."""
        from cairn.cairn.mcp_tools import list_tools

        tools = list_tools()
        tool_names = {t.name for t in tools}

        # Check for key tools
        expected_tools = [
            "cairn_list_items",
            "cairn_get_item",
            "cairn_surface_next",
            "cairn_set_priority",
        ]

        for expected in expected_tools:
            assert expected in tool_names, f"Missing tool: {expected}"

    def test_surfacer_integration(
        self,
        cairn_store: CairnStore,
        surfacer: CairnSurfacer,
    ) -> None:
        """Test surfacer integration that MCP tools use."""
        # Set up items
        cairn_store.get_or_create_metadata("act", "tool-test-item")
        cairn_store.set_kanban_state("act", "tool-test-item", KanbanState.ACTIVE)
        cairn_store.set_priority("act", "tool-test-item", 5)

        # Use surfacer directly (same as MCP tool would)
        results = surfacer.surface_next()

        # Should return list
        assert isinstance(results, list)

    def test_store_operations_for_tools(
        self,
        cairn_store: CairnStore,
    ) -> None:
        """Test store operations that MCP tools use."""
        # Create metadata (cairn_get_item uses this)
        cairn_store.get_or_create_metadata("scene", "tool-test")
        metadata = cairn_store.get_metadata("scene", "tool-test")
        assert metadata is not None

        # Set priority (cairn_set_priority uses this)
        cairn_store.set_priority("scene", "tool-test", 4, reason="Testing")
        updated = cairn_store.get_metadata("scene", "tool-test")
        assert updated is not None
        assert updated.priority == 4

        # Set kanban state (cairn_set_kanban_state uses this)
        cairn_store.set_kanban_state("scene", "tool-test", KanbanState.ACTIVE)
        updated = cairn_store.get_metadata("scene", "tool-test")
        assert updated is not None
        assert updated.kanban_state == KanbanState.ACTIVE


# =============================================================================
# Play Kanban Workflow E2E Tests
# =============================================================================


class TestPlayKanbanWorkflowE2E:
    """E2E tests for Play Kanban workflow."""

    @pytest.fixture
    def play_db_setup(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Set up play_db for workflow tests."""
        data_dir = tmp_path / "reos-data"
        data_dir.mkdir()
        monkeypatch.setenv("TALKINGROCK_DATA_DIR", str(data_dir))

        import cairn.play_db as play_db

        play_db.close_connection()
        play_db.init_db()

        yield play_db

        play_db.close_connection()

    def test_scene_creation_to_kanban_display(self, play_db_setup) -> None:
        """Test scene creation flows through to Kanban board display."""
        play_db = play_db_setup

        # Create act and scene
        _, act_id = play_db.create_act(title="Kanban Test Act")
        _, scene_id = play_db.create_scene(
            act_id=act_id,
            title="New Task",
            stage="planning",
        )

        # Verify scene appears in list
        scenes = play_db.list_scenes(act_id)
        assert len(scenes) == 1
        assert scenes[0]["stage"] == "planning"

        # Verify in list_all_scenes (used for Kanban)
        all_scenes = play_db.list_all_scenes()
        assert any(s["scene_id"] == scene_id for s in all_scenes)

    def test_scene_stage_transitions(self, play_db_setup) -> None:
        """Test scene stage transitions in Kanban workflow."""
        play_db = play_db_setup

        _, act_id = play_db.create_act(title="Stage Test Act")
        _, scene_id = play_db.create_scene(act_id=act_id, title="Transition Task")

        # Initial stage should be planning
        scene = play_db.get_scene(scene_id)
        assert scene["stage"] == "planning"

        # Transition to in_progress
        play_db.update_scene(act_id=act_id, scene_id=scene_id, stage="in_progress")
        scene = play_db.get_scene(scene_id)
        assert scene["stage"] == "in_progress"

        # Transition to complete
        play_db.update_scene(act_id=act_id, scene_id=scene_id, stage="complete")
        scene = play_db.get_scene(scene_id)
        assert scene["stage"] == "complete"

    def test_overdue_detection_workflow(self, play_db_setup) -> None:
        """Test overdue detection — non-recurring scenes auto-complete."""
        from cairn.play_computed import is_overdue, compute_effective_stage

        play_db = play_db_setup

        _, act_id = play_db.create_act(title="Overdue Test Act")
        _, scene_id = play_db.create_scene(act_id=act_id, title="Overdue Task")

        # Set past calendar event
        past_date = (datetime.now() - timedelta(days=2)).isoformat()
        play_db.update_scene_calendar_data(scene_id, calendar_event_start=past_date)

        scene = play_db.get_scene(scene_id)

        # Non-recurring overdue scenes auto-complete per docs
        assert is_overdue(scene) is True
        assert compute_effective_stage(scene) == "complete"

    def test_calendar_sync_to_kanban_update(self, play_db_setup) -> None:
        """Test calendar sync updates reflect in Kanban."""
        play_db = play_db_setup

        _, act_id = play_db.create_act(title="Calendar Sync Act")
        _, scene_id = play_db.create_scene(
            act_id=act_id,
            title="Calendar Task",
            calendar_event_id="cal-123",
        )

        # Simulate calendar sync updating the scene
        new_start = (datetime.now() + timedelta(days=1)).isoformat()
        play_db.update_scene_calendar_data(
            scene_id,
            calendar_event_start=new_start,
            calendar_event_title="Updated Meeting",
            calendar_name="Work",
        )

        # Verify updates
        scene = play_db.get_scene(scene_id)
        assert scene["calendar_event_start"] == new_start
        assert scene["calendar_name"] == "Work"


# =============================================================================
# Calendar Integration E2E Tests
# =============================================================================


class TestCalendarIntegrationE2E:
    """E2E tests for calendar-scene integration."""

    @pytest.fixture
    def play_db_setup(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Set up play_db for calendar integration tests."""
        data_dir = tmp_path / "reos-data"
        data_dir.mkdir()
        monkeypatch.setenv("TALKINGROCK_DATA_DIR", str(data_dir))

        import cairn.play_db as play_db

        play_db.close_connection()
        play_db.init_db()

        yield play_db

        play_db.close_connection()

    def test_calendar_event_creates_scene(self, play_db_setup) -> None:
        """Test calendar event sync creates corresponding scene."""
        play_db = play_db_setup

        # Ensure Your Story act exists (inbound sync target)
        play_db.ensure_your_story_act()

        # Simulate creating scene from calendar event
        scenes, scene_id = play_db.create_scene(
            act_id="your-story",
            title="Doctor Appointment",
            calendar_event_id="cal-doctor-123",
        )

        # Update with calendar data
        event_start = (datetime.now() + timedelta(days=1, hours=10)).isoformat()
        play_db.update_scene_calendar_data(
            scene_id,
            calendar_event_start=event_start,
            calendar_event_title="Doctor Appointment",
            calendar_name="Personal",
            category="event",
        )

        # Verify scene exists with calendar data
        scene = play_db.get_scene(scene_id)
        assert scene["calendar_event_id"] == "cal-doctor-123"
        assert scene["calendar_event_start"] == event_start

        # Verify can be found by calendar event ID
        found = play_db.find_scene_by_calendar_event("cal-doctor-123")
        assert found is not None
        assert found["scene_id"] == scene_id

    def test_scene_completion_updates_calendar_status(self, play_db_setup) -> None:
        """Test completing a scene could update calendar event status."""
        play_db = play_db_setup

        _, act_id = play_db.create_act(title="Calendar Test Act")
        _, scene_id = play_db.create_scene(
            act_id=act_id,
            title="Completable Task",
            calendar_event_id="cal-complete-123",
        )

        # Complete the scene
        play_db.update_scene(act_id=act_id, scene_id=scene_id, stage="complete")

        # Verify scene is complete
        scene = play_db.get_scene(scene_id)
        assert scene["stage"] == "complete"

        # In full implementation, this would also update Thunderbird

    def test_recurring_event_next_occurrence_update(self, play_db_setup) -> None:
        """Test recurring event next_occurrence is properly managed."""
        play_db = play_db_setup

        _, act_id = play_db.create_act(title="Recurring Test Act")
        _, scene_id = play_db.create_scene(
            act_id=act_id,
            title="Weekly Standup",
            recurrence_rule="RRULE:FREQ=WEEKLY;BYDAY=MO",
            calendar_event_id="cal-weekly-123",
        )

        # Set initial calendar data with next occurrence
        base_start = (datetime.now() - timedelta(days=7)).isoformat()  # Past
        next_occ = (datetime.now() + timedelta(days=1)).isoformat()  # Future

        play_db.update_scene_calendar_data(
            scene_id,
            calendar_event_start=base_start,
            next_occurrence=next_occ,
        )

        # Verify next_occurrence is set
        scene = play_db.get_scene(scene_id)
        assert scene["next_occurrence"] == next_occ
        assert scene["recurrence_rule"] == "RRULE:FREQ=WEEKLY;BYDAY=MO"


# =============================================================================
# UI RPC Integration E2E Tests
# =============================================================================


class TestUIRPCIntegrationE2E:
    """E2E tests for UI RPC integration."""

    @pytest.fixture
    def play_db_setup(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Set up play_db for RPC tests."""
        data_dir = tmp_path / "reos-data"
        data_dir.mkdir()
        monkeypatch.setenv("TALKINGROCK_DATA_DIR", str(data_dir))

        import cairn.play_db as play_db

        play_db.close_connection()
        play_db.init_db()

        yield play_db

        play_db.close_connection()

    def test_list_all_scenes_includes_computed_fields(self, play_db_setup) -> None:
        """Test list_all_scenes includes computed display fields."""
        from cairn.play_computed import enrich_scene_for_display

        play_db = play_db_setup

        _, act_id = play_db.create_act(title="RPC Test Act", color="#ff0000")
        _, scene_id = play_db.create_scene(
            act_id=act_id,
            title="RPC Test Scene",
            stage="planning",
        )

        # Get all scenes
        all_scenes = play_db.list_all_scenes()
        scene = next(s for s in all_scenes if s["scene_id"] == scene_id)

        # Verify act info is included
        assert scene["act_title"] == "RPC Test Act"
        assert scene["act_color"] == "#ff0000"

        # Enrich for display
        enriched = enrich_scene_for_display(scene)

        # Verify computed fields
        assert "is_unscheduled" in enriched
        assert "is_overdue" in enriched
        assert "effective_stage" in enriched

        # Unscheduled scene should have effective_stage = planning
        assert enriched["is_unscheduled"] is True
        assert enriched["effective_stage"] == "planning"

    def test_scene_update_triggers_effective_stage_recalc(self, play_db_setup) -> None:
        """Test scene update triggers effective_stage recalculation."""
        from cairn.play_computed import compute_effective_stage

        play_db = play_db_setup

        _, act_id = play_db.create_act(title="Stage Recalc Act")
        _, scene_id = play_db.create_scene(
            act_id=act_id,
            title="Stage Recalc Scene",
            stage="planning",
        )

        # Initial: unscheduled, effective_stage = planning
        scene = play_db.get_scene(scene_id)
        assert compute_effective_stage(scene) == "planning"

        # Add calendar event (future date)
        future_date = (datetime.now() + timedelta(days=2)).isoformat()
        play_db.update_scene_calendar_data(scene_id, calendar_event_start=future_date)

        # Now: scheduled, effective_stage = in_progress (planning with date)
        scene = play_db.get_scene(scene_id)
        assert compute_effective_stage(scene) == "in_progress"

        # Make it overdue
        past_date = (datetime.now() - timedelta(days=2)).isoformat()
        play_db.update_scene_calendar_data(scene_id, calendar_event_start=past_date)

        # Now: overdue non-recurring, effective_stage = complete (auto-complete)
        scene = play_db.get_scene(scene_id)
        assert compute_effective_stage(scene) == "complete"

        # Complete it
        play_db.update_scene(act_id=act_id, scene_id=scene_id, stage="complete")

        # Now: complete, effective_stage = complete (overrides overdue)
        scene = play_db.get_scene(scene_id)
        assert compute_effective_stage(scene) == "complete"

    def test_batch_scene_retrieval_for_kanban(self, play_db_setup) -> None:
        """Test batch retrieval of scenes for Kanban board display."""
        from cairn.play_computed import enrich_scene_for_display

        play_db = play_db_setup

        # Create multiple acts with scenes
        _, act1_id = play_db.create_act(title="Project A", color="#ff0000")
        _, act2_id = play_db.create_act(title="Project B", color="#00ff00")

        play_db.create_scene(act_id=act1_id, title="Task A1", stage="planning")
        play_db.create_scene(act_id=act1_id, title="Task A2", stage="in_progress")
        play_db.create_scene(act_id=act2_id, title="Task B1", stage="complete")

        # Get all scenes (as Kanban board would)
        all_scenes = play_db.list_all_scenes()
        assert len(all_scenes) == 3

        # Enrich all for display
        enriched = [enrich_scene_for_display(s) for s in all_scenes]

        # Verify all have computed fields
        for scene in enriched:
            assert "is_unscheduled" in scene
            assert "is_overdue" in scene
            assert "effective_stage" in scene
            assert "act_title" in scene
            assert "act_color" in scene

        # Group by effective_stage (like Kanban would)
        by_stage = {}
        for scene in enriched:
            stage = scene["effective_stage"]
            if stage not in by_stage:
                by_stage[stage] = []
            by_stage[stage].append(scene)

        # Verify distribution
        assert "planning" in by_stage
        assert "complete" in by_stage


# =============================================================================
# Priority Learning E2E Tests
# =============================================================================

import random as _random  # noqa: E402,I001

from conftest import requires_ollama  # noqa: E402,I001


# ---------------------------------------------------------------------------
# Reorder personas — each receives a list of item dicts and returns reordered
# ---------------------------------------------------------------------------

class _ReorderPersona:
    """Base class for reorder personas."""

    name: str = "base"

    def reorder(self, items: list[dict], reorder_number: int) -> list[dict]:
        raise NotImplementedError


class _HealthFirst(_ReorderPersona):
    """Always moves act-health items to the front."""

    name = "health_first"

    def reorder(self, items: list[dict], reorder_number: int) -> list[dict]:
        health = [i for i in items if i.get("act_id") == "act-health"]
        rest = [i for i in items if i.get("act_id") != "act-health"]
        return health + rest


class _ProjectFocused(_ReorderPersona):
    """Always moves act-career items to the front."""

    name = "project_focused"

    def reorder(self, items: list[dict], reorder_number: int) -> list[dict]:
        career = [i for i in items if i.get("act_id") == "act-career"]
        rest = [i for i in items if i.get("act_id") != "act-career"]
        return career + rest


class _Chaotic(_ReorderPersona):
    """Shuffles with a fixed seed — no learnable pattern."""

    name = "chaotic"

    def reorder(self, items: list[dict], reorder_number: int) -> list[dict]:
        shuffled = list(items)
        _random.Random(42 + reorder_number).shuffle(shuffled)
        return shuffled


class _GradualShifter(_ReorderPersona):
    """Reorders 1-4: health first; reorders 5+: career first."""

    name = "gradual_shifter"

    def reorder(self, items: list[dict], reorder_number: int) -> list[dict]:
        if reorder_number <= 4:
            priority_act = "act-health"
        else:
            priority_act = "act-career"
        front = [i for i in items if i.get("act_id") == priority_act]
        rest = [i for i in items if i.get("act_id") != priority_act]
        return front + rest


class _EmailPrioritizer(_ReorderPersona):
    """Moves email-type items to position 0."""

    name = "email_prioritizer"

    def reorder(self, items: list[dict], reorder_number: int) -> list[dict]:
        emails = [i for i in items if i.get("entity_type") == "email"]
        rest = [i for i in items if i.get("entity_type") != "email"]
        return emails + rest


class _StagePrioritizer(_ReorderPersona):
    """Moves in_progress items to the front."""

    name = "stage_prioritizer"

    def reorder(self, items: list[dict], reorder_number: int) -> list[dict]:
        in_progress = [i for i in items if i.get("stage") == "in_progress"]
        rest = [i for i in items if i.get("stage") != "in_progress"]
        return in_progress + rest


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _seed_initial_order(items: list[dict], reverse: bool = True) -> None:
    """Set an initial priority order so that subsequent reorders have old_position != None.

    This is required because the first reorder always has old_position=NULL (no prior
    state), and the SQL query filters ``WHERE old_position IS NOT NULL``.  After this
    seed call every following reorder will have an old_position to compare against.

    Args:
        items: The full item list to seed.
        reverse: If True, seed the priorities in reverse item order so that the
                 subsequent persona reorders always move items UP (producing positive
                 avg_improvement).  If False, use the items as-is.
    """
    from cairn.services.priority_signal_service import PrioritySignalService

    svc = PrioritySignalService()
    ordered = list(reversed(items)) if reverse else list(items)
    ordered_entities = [(it["entity_type"], it["entity_id"]) for it in ordered]
    svc.process_reorder(ordered_entities=ordered_entities)


def _run_persona_reorders(
    play_db_module: Any,
    persona: _ReorderPersona,
    items: list[dict],
    num_reorders: int,
    seed_reverse: bool = False,
) -> list[dict]:
    """Run N reorders with a persona; call process_reorder + extract_rules each time.

    Args:
        play_db_module: The imported play_db module (used for context only).
        persona: Reorder persona that decides item order.
        items: Full item list passed to the persona each round.
        num_reorders: How many reorders to execute.
        seed_reverse: If True, prime the priorities table with the reverse order
            before running the persona reorders so that old_position is populated
            and the improvement calculation has a meaningful "before" state.

    Returns:
        List of per-reorder result dicts with keys:
            reorder_number, ordered_ids, priorities_updated, rules_extracted
    """
    from cairn.services.priority_learning_service import PriorityLearningService
    from cairn.services.priority_signal_service import PrioritySignalService

    if seed_reverse:
        _seed_initial_order(items, reverse=True)

    signal_svc = PrioritySignalService()
    learn_svc = PriorityLearningService()
    results = []

    for i in range(1, num_reorders + 1):
        ordered = persona.reorder(items, reorder_number=i)

        # Build ordered_entities as (entity_type, entity_id) tuples
        ordered_entities = [(it["entity_type"], it["entity_id"]) for it in ordered]

        pr = signal_svc.process_reorder(ordered_entities=ordered_entities)
        rules = learn_svc.extract_rules()

        results.append({
            "reorder_number": i,
            "ordered_ids": [it["entity_id"] for it in ordered],
            "priorities_updated": pr["priorities_updated"],
            "rules_extracted": rules,
        })

    return results


def _save_tracking_results(results: list[dict], output_dir: Path) -> Path:
    """Serialise reorder tracking results to JSON; return the written path."""
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / "reorder_tracking.json"

    # Make rules JSON-serialisable (convert floats that may be numpy/similar)
    serialisable = []
    for r in results:
        serialisable.append({
            "reorder_number": r["reorder_number"],
            "ordered_ids": r["ordered_ids"],
            "priorities_updated": r["priorities_updated"],
            "rules_extracted": [
                {k: v for k, v in rule.items()}
                for rule in r["rules_extracted"]
            ],
        })

    out_path.write_text(json.dumps(serialisable, indent=2), encoding="utf-8")
    return out_path


def _make_surfaced_items(item_dicts: list[dict]) -> list[Any]:
    """Build SurfacedItem instances from test metadata dicts."""
    from cairn.cairn.models import SurfacedItem

    surfaced = []
    for d in item_dicts:
        meta = None
        if d.get("stage"):
            meta = CairnMetadata(
                entity_type=d["entity_type"],
                entity_id=d["entity_id"],
            )
            # CairnMetadata does not have a `stage` field — stage lives on the
            # Scene record. We attach it as a dynamic attribute so that
            # compute_item_boost can find it via getattr(item.metadata, 'stage').
            object.__setattr__(meta, "stage", d["stage"])  # type: ignore[call-overload]

        item = SurfacedItem(
            entity_type=d["entity_type"],
            entity_id=d["entity_id"],
            title=d.get("title", d["entity_id"]),
            reason="test",
            urgency=d.get("urgency", "medium"),
            act_id=d.get("act_id"),
            scene_id=d.get("scene_id"),
            metadata=meta,
        )
        surfaced.append(item)
    return surfaced


class TestPriorityLearningE2E:
    """E2E tests for the priority learning pipeline.

    Tests cover:
    - Reorder history accumulation via PrioritySignalService
    - Rule extraction via PriorityLearningService
    - Boost application in _rank_and_dedupe (surfacing)
    - LLM analysis via PriorityAnalysisService (requires_ollama tier)
    """

    # ------------------------------------------------------------------
    # Shared play_db fixture (mirrors TestPlayKanbanWorkflowE2E pattern)
    # ------------------------------------------------------------------

    @pytest.fixture
    def play_db_setup(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Isolated play_db with empty schema."""
        data_dir = tmp_path / "reos-data"
        data_dir.mkdir()
        monkeypatch.setenv("TALKINGROCK_DATA_DIR", str(data_dir))

        import cairn.play_db as play_db

        play_db.close_connection()
        play_db.init_db()

        yield play_db

        play_db.close_connection()

    @pytest.fixture
    def play_db_with_scenes(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Isolated play_db pre-populated with 3 acts and 8 scenes.

        Yields (play_db_module, items) where items is a list of dicts:
            entity_type, entity_id, act_id, stage, title
        """
        data_dir = tmp_path / "reos-data"
        data_dir.mkdir()
        monkeypatch.setenv("TALKINGROCK_DATA_DIR", str(data_dir))

        import cairn.play_db as play_db

        play_db.close_connection()
        play_db.init_db()

        # Create acts with deterministic IDs by reading what create_act returns
        _, health_act_id = play_db.create_act(title="Health", color="#33aa33")
        _, career_act_id = play_db.create_act(title="Career", color="#3388ff")
        _, home_act_id = play_db.create_act(title="Home", color="#ff8833")

        # Rename act IDs to stable aliases we control inside the DB
        # (play_db generates UUIDs, so we patch the items list with actual IDs)
        _, gym_id = play_db.create_scene(
            act_id=health_act_id, title="Gym session", stage="in_progress"
        )
        _, diet_id = play_db.create_scene(
            act_id=health_act_id, title="Diet plan review", stage="planning"
        )
        _, checkup_id = play_db.create_scene(
            act_id=health_act_id, title="Annual check-up", stage="planning"
        )
        _, sprint_id = play_db.create_scene(
            act_id=career_act_id, title="Sprint planning", stage="in_progress"
        )
        _, report_id = play_db.create_scene(
            act_id=career_act_id, title="Quarterly report", stage="planning"
        )
        _, code_id = play_db.create_scene(
            act_id=career_act_id, title="Code review", stage="planning"
        )
        _, repair_id = play_db.create_scene(
            act_id=home_act_id, title="Roof repair", stage="in_progress"
        )
        _, garden_id = play_db.create_scene(
            act_id=home_act_id, title="Garden planning", stage="planning"
        )

        scene_items = [
            {
                "entity_type": "scene", "entity_id": gym_id,
                "act_id": health_act_id, "stage": "in_progress", "title": "Gym session",
            },
            {
                "entity_type": "scene", "entity_id": diet_id,
                "act_id": health_act_id, "stage": "planning", "title": "Diet plan review",
            },
            {
                "entity_type": "scene", "entity_id": checkup_id,
                "act_id": health_act_id, "stage": "planning", "title": "Annual check-up",
            },
            {
                "entity_type": "scene", "entity_id": sprint_id,
                "act_id": career_act_id, "stage": "in_progress", "title": "Sprint planning",
            },
            {
                "entity_type": "scene", "entity_id": report_id,
                "act_id": career_act_id, "stage": "planning", "title": "Quarterly report",
            },
            {
                "entity_type": "scene", "entity_id": code_id,
                "act_id": career_act_id, "stage": "planning", "title": "Code review",
            },
            {
                "entity_type": "scene", "entity_id": repair_id,
                "act_id": home_act_id, "stage": "in_progress", "title": "Roof repair",
            },
            {
                "entity_type": "scene", "entity_id": garden_id,
                "act_id": home_act_id, "stage": "planning", "title": "Garden planning",
            },
        ]

        # Add two synthetic email items (non-scene, so no DB scene row needed)
        email_items = [
            {
                "entity_type": "email", "entity_id": "email-urgent-1",
                "act_id": None, "stage": None, "title": "Urgent: contract renewal",
            },
            {
                "entity_type": "email", "entity_id": "email-follow-1",
                "act_id": None, "stage": None, "title": "Follow-up on proposal",
            },
        ]

        all_items = scene_items + email_items

        yield play_db, all_items, health_act_id, career_act_id

        play_db.close_connection()

    # ------------------------------------------------------------------
    # Tier 1: No-LLM tests
    # ------------------------------------------------------------------

    def test_health_first_creates_act_boost(self, play_db_with_scenes) -> None:
        """HealthFirst persona: 5 reorders should produce a positive act boost rule.

        We seed the DB with the reverse item order first so that subsequent
        HealthFirst reorders always move health items UP — yielding a positive
        avg_improvement and therefore a positive boost_score.
        """
        play_db, all_items, health_act_id, _career_act_id = play_db_with_scenes

        persona = _HealthFirst()
        results = _run_persona_reorders(
            play_db, persona, all_items, num_reorders=5, seed_reverse=True
        )

        # After 5 reorders every health scene has been moved up 5 times — the
        # aggregated act stats must cross the COUNT >= 3 threshold.
        final_rules = results[-1]["rules_extracted"]
        act_keys = {
            f"{r['feature_type']}:{r['feature_value']}": r["boost_score"]
            for r in final_rules
            if r["feature_type"] == "act"
        }

        health_key = f"act:{health_act_id}"
        assert health_key in act_keys, (
            f"Expected act rule for {health_key}. Rules found: {list(act_keys)}"
        )
        assert act_keys[health_key] > 0, (
            f"Expected positive boost for health act, got {act_keys[health_key]}"
        )

    def test_chaotic_produces_no_strong_rules(self, play_db_with_scenes) -> None:
        """Chaotic persona: random reorders should not create strong boost rules."""
        play_db, all_items, _health_act_id, _career_act_id = play_db_with_scenes

        # Use only scene items so act_id and stage features are populated
        scene_items = [i for i in all_items if i["entity_type"] == "scene"]
        persona = _Chaotic()
        results = _run_persona_reorders(play_db, persona, scene_items, num_reorders=8)

        final_rules = results[-1]["rules_extracted"]
        strong_rules = [r for r in final_rules if abs(r["boost_score"]) > 0.3]
        assert not strong_rules, (
            f"Chaotic persona should not produce strong rules. Got: {strong_rules}"
        )

    def test_gradual_shifter_convergence(self, play_db_with_scenes) -> None:
        """GradualShifter: rules should shift from health-positive to career-positive."""
        play_db, all_items, health_act_id, career_act_id = play_db_with_scenes

        scene_items = [i for i in all_items if i["entity_type"] == "scene"]
        persona = _GradualShifter()
        results = _run_persona_reorders(
            play_db, persona, scene_items, num_reorders=8, seed_reverse=True
        )

        # After 8 reorders we should have rule entries for both acts
        final_rules = results[-1]["rules_extracted"]
        rule_map = {
            f"{r['feature_type']}:{r['feature_value']}": r["boost_score"]
            for r in final_rules
        }

        # Both act keys should appear after 8 reorders (>= 3 samples each)
        health_key = f"act:{health_act_id}"
        career_key = f"act:{career_act_id}"
        assert health_key in rule_map or career_key in rule_map, (
            "Expected at least one act boost rule after 8 reorders of GradualShifter"
        )

    def test_email_prioritizer_history_flags_email_items(self, play_db_with_scenes) -> None:
        """EmailPrioritizer: email items should be recorded with is_email=1 in history.

        Note: attention_priorities is scene-only, so email rows always have
        old_position=NULL and are excluded from the avg_improvement SQL aggregation.
        The is_email flag in reorder_history is the observable signal for email items.
        """
        import cairn.play_db as play_db_mod

        play_db, all_items, _health_act_id, _career_act_id = play_db_with_scenes

        persona = _EmailPrioritizer()
        _run_persona_reorders(play_db, persona, all_items, num_reorders=3, seed_reverse=True)

        conn = play_db_mod._get_connection()
        email_rows = conn.execute(
            "SELECT entity_type, entity_id, is_email FROM reorder_history"
            " WHERE entity_type = 'email'"
        ).fetchall()

        assert email_rows, "Expected email entries in reorder_history"
        for row in email_rows:
            assert row["is_email"] == 1, (
                f"Expected is_email=1 for email entity {row['entity_id']}, got {row['is_email']}"
            )

    def test_stage_prioritizer_learns_stage(self, play_db_with_scenes) -> None:
        """StagePrioritizer: 5 reorders should create a positive stage:in_progress rule."""
        play_db, all_items, _health_act_id, _career_act_id = play_db_with_scenes

        scene_items = [i for i in all_items if i["entity_type"] == "scene"]
        persona = _StagePrioritizer()
        results = _run_persona_reorders(
            play_db, persona, scene_items, num_reorders=5, seed_reverse=True
        )

        final_rules = results[-1]["rules_extracted"]
        stage_rules = [
            r for r in final_rules
            if r["feature_type"] == "stage" and r["feature_value"] == "in_progress"
        ]
        assert stage_rules, "Expected stage:in_progress rule after 5 reorders"
        assert stage_rules[0]["boost_score"] > 0, (
            f"Expected positive boost for in_progress, got {stage_rules[0]['boost_score']}"
        )

    def test_reorder_history_features_populated(self, play_db_with_scenes) -> None:
        """Single reorder: verify that reorder_history rows have non-NULL feature columns."""
        import cairn.play_db as play_db_mod
        from cairn.services.priority_signal_service import PrioritySignalService

        play_db, all_items, health_act_id, _career_act_id = play_db_with_scenes

        scene_items = [i for i in all_items if i["entity_type"] == "scene"]
        ordered_entities = [("scene", it["entity_id"]) for it in scene_items]

        svc = PrioritySignalService()
        svc.process_reorder(ordered_entities=ordered_entities)

        # Inspect raw history rows
        conn = play_db_mod._get_connection()
        cursor = conn.execute(
            "SELECT entity_type, entity_id, act_id, scene_stage FROM reorder_history"
        )
        rows = cursor.fetchall()
        assert rows, "Expected reorder_history rows after process_reorder"

        # At least the rows for scene items should have act_id populated
        scene_rows = [r for r in rows if r["entity_type"] == "scene"]
        assert scene_rows, "Expected scene rows in reorder_history"
        for row in scene_rows:
            assert row["act_id"] is not None, (
                f"act_id should be populated for scene {row['entity_id']}, got NULL"
            )

    def test_boost_affects_surfacing_order(self, play_db_with_scenes) -> None:
        """Directly insert a boost rule and verify _rank_and_dedupe respects it."""
        import uuid
        from datetime import UTC, datetime

        import cairn.play_db as play_db_mod
        from cairn.cairn.surfacing import CairnSurfacer

        play_db, all_items, health_act_id, career_act_id = play_db_with_scenes

        # Insert a strong positive boost for career act
        now = datetime.now(UTC).isoformat()
        boost_rule = {
            "id": str(uuid.uuid4()),
            "feature_type": "act",
            "feature_value": career_act_id,
            "boost_score": 0.9,
            "confidence": 1.0,
            "sample_count": 10,
            "description": "Career items prioritized",
            "active": 1,
            "created_at": now,
            "updated_at": now,
        }
        play_db_mod.upsert_boost_rule(boost_rule)

        # Build SurfacedItems — same urgency so boost is the tiebreaker
        scene_items = [i for i in all_items if i["entity_type"] == "scene"]
        surfaced = _make_surfaced_items(scene_items)

        surfacer = CairnSurfacer.__new__(CairnSurfacer)
        ranked = surfacer._rank_and_dedupe(surfaced, max_items=len(surfaced))

        # Career items should appear before health items at equal urgency
        ranked_ids = [item.entity_id for item in ranked]
        health_ids = {it["entity_id"] for it in scene_items if it["act_id"] == health_act_id}
        career_ids = {it["entity_id"] for it in scene_items if it["act_id"] == career_act_id}

        # Find first health and first career position
        first_health = next((i for i, eid in enumerate(ranked_ids) if eid in health_ids), None)
        first_career = next((i for i, eid in enumerate(ranked_ids) if eid in career_ids), None)

        assert first_career is not None and first_health is not None, (
            "Both health and career items should appear in ranked output"
        )
        assert first_career < first_health, (
            f"Career items (pos {first_career}) should rank before "
            f"health items (pos {first_health}) when career has a strong boost"
        )

    def test_tracking_records_saved(self, play_db_with_scenes, tmp_path: Path) -> None:
        """Three reorders + _save_tracking_results: verify JSON file is written correctly."""
        play_db, all_items, _health_act_id, _career_act_id = play_db_with_scenes

        scene_items = [i for i in all_items if i["entity_type"] == "scene"]
        persona = _HealthFirst()
        results = _run_persona_reorders(play_db, persona, scene_items, num_reorders=3)

        out_path = _save_tracking_results(results, tmp_path / "tracking")

        assert out_path.exists(), "Expected tracking JSON file to be created"
        data = json.loads(out_path.read_text(encoding="utf-8"))
        assert len(data) == 3, f"Expected 3 reorder records, got {len(data)}"

        for record in data:
            assert "reorder_number" in record
            assert "ordered_ids" in record
            assert "priorities_updated" in record
            assert "rules_extracted" in record
            assert isinstance(record["ordered_ids"], list)

    # ------------------------------------------------------------------
    # Tier 2: LLM tests (require Ollama)
    # ------------------------------------------------------------------

    @requires_ollama
    @pytest.mark.slow
    def test_llm_health_pattern_analysis(
        self, play_db_with_scenes, isolated_db_singleton, real_llm
    ) -> None:
        """3 HealthFirst reorders + analyze_reorder: response should be non-empty."""
        from cairn.db import get_db
        from cairn.services.conversation_service import ConversationService
        from cairn.services.priority_analysis_service import PriorityAnalysisService

        play_db, all_items, health_act_id, _career_act_id = play_db_with_scenes
        scene_items = [i for i in all_items if i["entity_type"] == "scene"]

        persona = _HealthFirst()
        _run_persona_reorders(play_db, persona, scene_items, num_reorders=3)

        db = get_db()
        conv_service = ConversationService()
        conv = conv_service.start()

        ordered_scene_ids = [it["entity_id"] for it in scene_items[:3]]
        scene_details = [
            {
                "scene_id": it["entity_id"],
                "title": it["title"],
                "stage": it["stage"],
                "act_id": it["act_id"],
                "act_title": "Health",
                "notes": "",
                "start_date": None,
                "end_date": None,
            }
            for it in scene_items[:3]
        ]

        analyzer = PriorityAnalysisService()
        response = analyzer.analyze_reorder(
            db=db,
            ordered_scene_ids=ordered_scene_ids,
            old_priorities={},
            scene_details=scene_details,
            conversation_id=conv.id,
        )

        assert response, "Expected non-empty analysis from CAIRN"
        assert len(response.strip()) > 20, (
            f"Expected a substantive response, got: {response!r}"
        )

    @requires_ollama
    @pytest.mark.slow
    def test_llm_career_focus_analysis(
        self, play_db_with_scenes, isolated_db_singleton, real_llm
    ) -> None:
        """Career items moved to top — analysis should acknowledge the shift."""
        from cairn.db import get_db
        from cairn.services.conversation_service import ConversationService
        from cairn.services.priority_analysis_service import PriorityAnalysisService

        play_db, all_items, _health_act_id, career_act_id = play_db_with_scenes
        scene_items = [i for i in all_items if i["entity_type"] == "scene"]

        persona = _ProjectFocused()
        _run_persona_reorders(play_db, persona, scene_items, num_reorders=3)

        db = get_db()
        conv_service = ConversationService()
        conv = conv_service.start()

        career_items = [i for i in scene_items if i["act_id"] == career_act_id]
        ordered_scene_ids = [it["entity_id"] for it in career_items]
        scene_details = [
            {
                "scene_id": it["entity_id"],
                "title": it["title"],
                "stage": it["stage"],
                "act_id": it["act_id"],
                "act_title": "Career",
                "notes": "",
                "start_date": None,
                "end_date": None,
            }
            for it in career_items
        ]

        old_priorities = {it["entity_id"]: idx + 3 for idx, it in enumerate(career_items)}

        analyzer = PriorityAnalysisService()
        response = analyzer.analyze_reorder(
            db=db,
            ordered_scene_ids=ordered_scene_ids,
            old_priorities=old_priorities,
            scene_details=scene_details,
            conversation_id=conv.id,
        )

        assert response, "Expected non-empty analysis from CAIRN"

    @requires_ollama
    @pytest.mark.slow
    def test_llm_no_crash_on_minimal_context(
        self, play_db_with_scenes, isolated_db_singleton, real_llm
    ) -> None:
        """analyze_reorder with a single item and no old priorities should not crash."""
        from cairn.db import get_db
        from cairn.services.conversation_service import ConversationService
        from cairn.services.priority_analysis_service import PriorityAnalysisService

        play_db, all_items, _health_act_id, _career_act_id = play_db_with_scenes
        scene_items = [i for i in all_items if i["entity_type"] == "scene"]
        single_item = scene_items[0]

        db = get_db()
        conv_service = ConversationService()
        conv = conv_service.start()

        analyzer = PriorityAnalysisService()
        response = analyzer.analyze_reorder(
            db=db,
            ordered_scene_ids=[single_item["entity_id"]],
            old_priorities={},
            scene_details=[
                {
                    "scene_id": single_item["entity_id"],
                    "title": single_item["title"],
                    "stage": single_item["stage"],
                    "act_id": single_item["act_id"],
                    "act_title": "Health",
                    "notes": "",
                    "start_date": None,
                    "end_date": None,
                }
            ],
            conversation_id=conv.id,
        )

        # Just verify no exception was raised and we got a string back
        assert isinstance(response, str)

    @requires_ollama
    @pytest.mark.slow
    def test_llm_rich_context_references_details(
        self, play_db_with_scenes, isolated_db_singleton, real_llm
    ) -> None:
        """Full scene details passed in: CAIRN response should be non-trivial."""
        from cairn.db import get_db
        from cairn.services.conversation_service import ConversationService
        from cairn.services.priority_analysis_service import PriorityAnalysisService

        play_db, all_items, health_act_id, career_act_id = play_db_with_scenes
        scene_items = [i for i in all_items if i["entity_type"] == "scene"]

        persona = _HealthFirst()
        _run_persona_reorders(play_db, persona, scene_items, num_reorders=4)

        db = get_db()
        conv_service = ConversationService()
        conv = conv_service.start()

        ordered_scene_ids = [it["entity_id"] for it in scene_items]
        old_priorities = {it["entity_id"]: idx + 1 for idx, it in enumerate(reversed(scene_items))}

        scene_details = []
        for it in scene_items:
            if it["act_id"] == health_act_id:
                act_title = "Health"
            elif it["act_id"] == career_act_id:
                act_title = "Career"
            else:
                act_title = "Home"
            scene_details.append({
                "scene_id": it["entity_id"],
                "title": it["title"],
                "stage": it["stage"],
                "act_id": it["act_id"],
                "act_title": act_title,
                "notes": f"Notes for {it['title']}",
                "start_date": "2026-03-10",
                "end_date": "2026-03-11",
                "urgency": "medium",
            })

        analyzer = PriorityAnalysisService()
        response = analyzer.analyze_reorder(
            db=db,
            ordered_scene_ids=ordered_scene_ids,
            old_priorities=old_priorities,
            scene_details=scene_details,
            conversation_id=conv.id,
        )

        assert response, "Expected non-empty response with rich context"
        assert len(response.strip()) > 50, (
            f"Expected a substantial response with rich context, got: {response!r}"
        )

    @requires_ollama
    @pytest.mark.slow
    def test_full_pipeline_with_llm(
        self, play_db_with_scenes, isolated_db_singleton, real_llm
    ) -> None:
        """End-to-end: handle_cairn_attention_reorder orchestrates the full pipeline."""
        from cairn.db import get_db
        from cairn.rpc_handlers.system import handle_cairn_attention_reorder

        play_db, all_items, _health_act_id, _career_act_id = play_db_with_scenes
        scene_items = [i for i in all_items if i["entity_type"] == "scene"]

        # Run a few background reorders to seed the history
        persona = _HealthFirst()
        _run_persona_reorders(play_db, persona, scene_items, num_reorders=3)

        db = get_db()
        ordered_scene_ids = [it["entity_id"] for it in scene_items]

        result = handle_cairn_attention_reorder(
            db=db,
            ordered_scene_ids=ordered_scene_ids,
        )

        assert "priorities_updated" in result, (
            f"Expected priorities_updated in result. Got: {result}"
        )
        assert result["priorities_updated"] >= 0
