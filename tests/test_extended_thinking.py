"""Tests for CAIRN Extended Thinking module."""

from __future__ import annotations

import json
import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from reos.cairn.extended_thinking import (
    ThinkingNode,
    FacetCheck,
    Tension,
    ExtendedThinkingTrace,
    CAIRNExtendedThinking,
)


class TestThinkingNode:
    """Tests for ThinkingNode dataclass."""

    def test_create_simple_node(self):
        """Test creating a simple thinking node."""
        node = ThinkingNode(
            content="User wants to change careers",
            node_type="understood",
            confidence=0.9,
        )
        assert node.content == "User wants to change careers"
        assert node.node_type == "understood"
        assert node.confidence == 0.9
        assert node.children == []

    def test_create_node_with_children(self):
        """Test creating a node with children."""
        child1 = ThinkingNode(content="Option A", node_type="reasoning_step", confidence=0.5)
        child2 = ThinkingNode(content="Option B", node_type="reasoning_step", confidence=0.5)
        parent = ThinkingNode(
            content="Multiple options exist",
            node_type="ambiguous",
            confidence=0.5,
            children=[child1, child2],
        )
        assert len(parent.children) == 2
        assert parent.children[0].content == "Option A"

    def test_to_dict(self):
        """Test serialization to dict."""
        node = ThinkingNode(
            content="Test content",
            node_type="assumption",
            confidence=0.7,
        )
        data = node.to_dict()
        assert data == {
            "content": "Test content",
            "type": "assumption",
            "confidence": 0.7,
            "children": [],
        }

    def test_to_dict_with_nested_children(self):
        """Test serialization with nested children."""
        grandchild = ThinkingNode(content="Grandchild", node_type="reasoning_step", confidence=0.3)
        child = ThinkingNode(
            content="Child",
            node_type="reasoning_step",
            confidence=0.5,
            children=[grandchild],
        )
        parent = ThinkingNode(
            content="Parent",
            node_type="ambiguous",
            confidence=0.5,
            children=[child],
        )
        data = parent.to_dict()
        assert len(data["children"]) == 1
        assert len(data["children"][0]["children"]) == 1
        assert data["children"][0]["children"][0]["content"] == "Grandchild"

    def test_from_dict(self):
        """Test deserialization from dict."""
        data = {
            "content": "Restored node",
            "type": "identity_check",
            "confidence": 0.8,
            "children": [],
        }
        node = ThinkingNode.from_dict(data)
        assert node.content == "Restored node"
        assert node.node_type == "identity_check"
        assert node.confidence == 0.8

    def test_roundtrip_serialization(self):
        """Test that to_dict/from_dict is lossless."""
        original = ThinkingNode(
            content="Test",
            node_type="tension",
            confidence=0.6,
            children=[
                ThinkingNode(content="Child", node_type="reasoning_step", confidence=0.4)
            ],
        )
        data = original.to_dict()
        restored = ThinkingNode.from_dict(data)
        assert restored.content == original.content
        assert restored.node_type == original.node_type
        assert restored.confidence == original.confidence
        assert len(restored.children) == 1


class TestFacetCheck:
    """Tests for FacetCheck dataclass."""

    def test_create_facet_check(self):
        """Test creating a facet check."""
        check = FacetCheck(
            facet_name="career_goals",
            facet_source="me.md",
            reasoning_branch="User wants to be a teacher",
            alignment=0.85,
            explanation="Aligns with stated goal of teaching others",
        )
        assert check.facet_name == "career_goals"
        assert check.alignment == 0.85

    def test_to_dict(self):
        """Test serialization."""
        check = FacetCheck(
            facet_name="values",
            facet_source="Act: Career",
            reasoning_branch="Prioritizing income",
            alignment=-0.3,
            explanation="Conflicts with stated value of work-life balance",
        )
        data = check.to_dict()
        assert data["facet_name"] == "values"
        assert data["alignment"] == -0.3

    def test_from_dict(self):
        """Test deserialization."""
        data = {
            "facet_name": "test_facet",
            "facet_source": "test_source",
            "reasoning_branch": "test_branch",
            "alignment": 0.5,
            "explanation": "test explanation",
        }
        check = FacetCheck.from_dict(data)
        assert check.facet_name == "test_facet"


class TestTension:
    """Tests for Tension dataclass."""

    def test_create_tension(self):
        """Test creating a tension."""
        tension = Tension(
            description="Career change conflicts with stated desire to slow down",
            identity_facet="life_pace",
            prompt_aspect="career change discussion",
            severity="medium",
            recommendation="Clarify which priority takes precedence",
        )
        assert tension.severity == "medium"
        assert "conflicts" in tension.description

    def test_to_dict(self):
        """Test serialization."""
        tension = Tension(
            description="Test tension",
            identity_facet="test_facet",
            prompt_aspect="test_aspect",
            severity="high",
            recommendation="Test recommendation",
        )
        data = tension.to_dict()
        assert data["severity"] == "high"

    def test_from_dict(self):
        """Test deserialization."""
        data = {
            "description": "Restored tension",
            "identity_facet": "facet",
            "prompt_aspect": "aspect",
            "severity": "low",
            "recommendation": "rec",
        }
        tension = Tension.from_dict(data)
        assert tension.description == "Restored tension"


class TestExtendedThinkingTrace:
    """Tests for ExtendedThinkingTrace dataclass."""

    def test_create_trace(self):
        """Test creating a new trace."""
        trace = ExtendedThinkingTrace.create("What should I do about my career?")
        assert trace.prompt == "What should I do about my career?"
        assert trace.trace_id.startswith("trace-")
        assert trace.started_at is not None
        assert trace.completed_at is None

    def test_complete_trace(self):
        """Test completing a trace."""
        trace = ExtendedThinkingTrace.create("Test prompt")
        assert trace.completed_at is None
        trace.complete()
        assert trace.completed_at is not None

    def test_summary(self):
        """Test summary generation."""
        trace = ExtendedThinkingTrace.create("Test")
        trace.understood = [
            ThinkingNode(content="A", node_type="understood", confidence=0.9),
            ThinkingNode(content="B", node_type="understood", confidence=0.8),
        ]
        trace.ambiguous = [
            ThinkingNode(content="C", node_type="ambiguous", confidence=0.5),
        ]
        trace.assumptions = [
            ThinkingNode(content="D", node_type="assumption", confidence=0.6),
        ]
        trace.tensions = [
            Tension(
                description="E",
                identity_facet="f",
                prompt_aspect="g",
                severity="low",
                recommendation="h",
            ),
        ]
        trace.questions_for_user = ["What do you mean by X?"]

        summary = trace.summary()
        assert summary["understood_count"] == 2
        assert summary["ambiguous_count"] == 1
        assert summary["assumption_count"] == 1
        assert summary["tension_count"] == 1
        assert summary["questions_count"] == 1

    def test_to_dict(self):
        """Test full serialization."""
        trace = ExtendedThinkingTrace.create("Test prompt")
        trace.understood = [
            ThinkingNode(content="Understood item", node_type="understood", confidence=0.9)
        ]
        trace.decision = "respond"
        trace.final_confidence = 0.85
        trace.complete()

        data = trace.to_dict()
        assert data["prompt"] == "Test prompt"
        assert len(data["understood"]) == 1
        assert data["decision"] == "respond"
        assert data["final_confidence"] == 0.85

    def test_from_dict(self):
        """Test deserialization."""
        data = {
            "trace_id": "trace-abc123",
            "prompt": "Original prompt",
            "started_at": "2025-01-01T12:00:00+00:00",
            "completed_at": "2025-01-01T12:00:05+00:00",
            "understood": [{"content": "A", "type": "understood", "confidence": 0.9}],
            "ambiguous": [],
            "unknowns": [],
            "questions_for_user": ["Q1?"],
            "assumptions": [],
            "facets_to_check": ["values"],
            "identity_facets_checked": [],
            "tensions": [],
            "final_response": "Here is my response",
            "final_confidence": 0.8,
            "decision": "respond",
        }
        trace = ExtendedThinkingTrace.from_dict(data)
        assert trace.trace_id == "trace-abc123"
        assert trace.prompt == "Original prompt"
        assert len(trace.understood) == 1
        assert trace.questions_for_user == ["Q1?"]
        assert trace.final_confidence == 0.8

    def test_format_for_display(self):
        """Test text formatting for chat display."""
        trace = ExtendedThinkingTrace.create("Test")
        trace.understood = [
            ThinkingNode(content="User wants help", node_type="understood", confidence=0.9)
        ]
        trace.assumptions = [
            ThinkingNode(content="User means career help", node_type="assumption", confidence=0.7)
        ]

        formatted = trace.format_for_display()
        assert "**Understood:**" in formatted
        assert "User wants help" in formatted
        assert "**Assumptions I made:**" in formatted
        assert "70%" in formatted


class TestCAIRNExtendedThinking:
    """Tests for CAIRNExtendedThinking engine."""

    @pytest.fixture
    def mock_identity(self):
        """Create a mock identity model."""
        identity = MagicMock()
        identity.facets = [
            MagicMock(name="career_goals", weight=2.0),
            MagicMock(name="values", weight=1.5),
        ]
        identity.get_relevant_facets = MagicMock(return_value=[])
        return identity

    @pytest.fixture
    def mock_llm(self):
        """Create a mock LLM provider."""
        llm = MagicMock()
        llm.chat_json = MagicMock(return_value='{"understood": [], "ambiguous": [], "unknowns": []}')
        return llm

    def test_trigger_phrases(self, mock_identity, mock_llm):
        """Test that trigger phrases activate extended thinking."""
        engine = CAIRNExtendedThinking(identity=mock_identity, llm=mock_llm)

        assert engine.should_auto_trigger("Think carefully about my career options")
        assert engine.should_auto_trigger("I need you to reflect on this decision")
        assert engine.should_auto_trigger("Please consider deeply what I should do")

    def test_no_trigger_for_simple_prompts(self, mock_identity, mock_llm):
        """Test that simple prompts don't trigger extended thinking."""
        engine = CAIRNExtendedThinking(identity=mock_identity, llm=mock_llm)

        assert not engine.should_auto_trigger("Hello")
        assert not engine.should_auto_trigger("What time is it?")
        assert not engine.should_auto_trigger("Thanks for your help")

    def test_trigger_for_identity_keywords(self, mock_identity, mock_llm):
        """Test that identity-related prompts trigger extended thinking."""
        engine = CAIRNExtendedThinking(identity=mock_identity, llm=mock_llm)

        assert engine.should_auto_trigger("Should I change my career direction?")
        assert engine.should_auto_trigger("What's my priority here? Is this important to me?")
        assert engine.should_auto_trigger("My goal is to find meaning in my life")

    def test_quick_ambiguity_scan(self, mock_identity, mock_llm):
        """Test the quick ambiguity heuristic."""
        engine = CAIRNExtendedThinking(identity=mock_identity, llm=mock_llm)

        # Low ambiguity
        score = engine._quick_ambiguity_scan("Open the file")
        assert score < 2

        # Medium ambiguity
        score = engine._quick_ambiguity_scan("Maybe we could try something else or perhaps another approach")
        assert score >= 2

        # High ambiguity
        score = engine._quick_ambiguity_scan(
            "I'm not sure what if maybe I could sort of try something and perhaps do this or that"
        )
        assert score >= 3

    def test_think_returns_trace(self, mock_identity, mock_llm):
        """Test that think() returns a complete trace."""
        # Mock LLM responses for each phase
        mock_llm.chat_json = MagicMock(side_effect=[
            # Phase 1: Comprehension
            json.dumps({
                "understood": [{"content": "User wants help", "confidence": 0.9}],
                "ambiguous": [],
                "unknowns": [],
            }),
            # Phase 2: Decomposition
            json.dumps({
                "questions": [],
                "assumptions": [],
                "facets_to_check": [],
            }),
        ])

        # Mock coherence verifier - patch where it's imported
        with patch("reos.cairn.coherence.CoherenceVerifier") as mock_verifier_class:
            mock_verifier = MagicMock()
            mock_result = MagicMock()
            mock_result.overall_score = 0.8
            mock_result.checks = []
            mock_verifier.verify = MagicMock(return_value=mock_result)
            mock_verifier_class.return_value = mock_verifier

            engine = CAIRNExtendedThinking(identity=mock_identity, llm=mock_llm)
            trace = engine.think("Help me with my career")

            assert trace.trace_id.startswith("trace-")
            assert trace.prompt == "Help me with my career"
            assert trace.completed_at is not None
            assert trace.decision in ["respond", "ask", "defer"]

    def test_should_ask_low_confidence(self, mock_identity, mock_llm):
        """Test that low confidence assumptions trigger asking."""
        engine = CAIRNExtendedThinking(identity=mock_identity, llm=mock_llm)
        trace = ExtendedThinkingTrace.create("Test")

        low_confidence = ThinkingNode(
            content="User means X",
            node_type="assumption",
            confidence=0.4,
        )
        assert engine.should_ask(low_confidence, trace) is True

    def test_should_ask_high_confidence(self, mock_identity, mock_llm):
        """Test that high confidence can skip asking (when not identity-affecting)."""
        mock_identity.get_relevant_facets = MagicMock(return_value=[
            MagicMock(weight=2.0)  # Strong prior signal
        ])

        engine = CAIRNExtendedThinking(identity=mock_identity, llm=mock_llm)
        trace = ExtendedThinkingTrace.create("Test")

        high_confidence = ThinkingNode(
            content="User wants a list",  # Not identity-affecting
            node_type="assumption",
            confidence=0.9,
        )
        assert engine.should_ask(high_confidence, trace) is False

    def test_should_ask_identity_affecting(self, mock_identity, mock_llm):
        """Test that identity-affecting assumptions trigger asking."""
        engine = CAIRNExtendedThinking(identity=mock_identity, llm=mock_llm)
        trace = ExtendedThinkingTrace.create("Test")

        identity_affecting = ThinkingNode(
            content="User's goal is to become a teacher",
            node_type="assumption",
            confidence=0.9,
        )
        assert engine.should_ask(identity_affecting, trace) is True


class TestExtendedThinkingStoreIntegration:
    """Tests for extended thinking trace persistence."""

    @pytest.fixture
    def store(self, tmp_path):
        """Create a temporary CAIRN store."""
        from reos.cairn.store import CairnStore
        return CairnStore(tmp_path / "cairn.db")

    def test_save_and_retrieve_trace(self, store):
        """Test saving and retrieving a trace."""
        trace = ExtendedThinkingTrace.create("Test prompt for storage")
        trace.understood = [
            ThinkingNode(content="Understood item", node_type="understood", confidence=0.9)
        ]
        trace.decision = "respond"
        trace.final_confidence = 0.85
        trace.complete()

        # Save
        store.save_extended_thinking_trace(
            trace_id=trace.trace_id,
            conversation_id="conv-123",
            message_id="msg-456",
            prompt=trace.prompt,
            started_at=trace.started_at,
            completed_at=trace.completed_at,
            trace_json=json.dumps(trace.to_dict()),
            summary=trace.summary(),
            decision=trace.decision,
            final_confidence=trace.final_confidence,
        )

        # Retrieve
        retrieved = store.get_extended_thinking_trace(trace.trace_id)
        assert retrieved is not None
        assert retrieved["prompt"] == "Test prompt for storage"
        assert retrieved["decision"] == "respond"
        assert retrieved["final_confidence"] == 0.85

    def test_list_traces(self, store):
        """Test listing traces with filters."""
        # Save multiple traces
        for i in range(3):
            trace = ExtendedThinkingTrace.create(f"Prompt {i}")
            trace.decision = "respond" if i < 2 else "ask"
            trace.final_confidence = 0.7 + i * 0.1
            trace.complete()

            store.save_extended_thinking_trace(
                trace_id=trace.trace_id,
                conversation_id="conv-test",
                message_id=f"msg-{i}",
                prompt=trace.prompt,
                started_at=trace.started_at,
                completed_at=trace.completed_at,
                trace_json=json.dumps(trace.to_dict()),
                summary=trace.summary(),
                decision=trace.decision,
                final_confidence=trace.final_confidence,
            )

        # List all
        all_traces = store.list_extended_thinking_traces(conversation_id="conv-test")
        assert len(all_traces) == 3

        # Filter by decision
        respond_traces = store.list_extended_thinking_traces(
            conversation_id="conv-test",
            decision="respond",
        )
        assert len(respond_traces) == 2

    def test_delete_trace(self, store):
        """Test deleting a trace."""
        trace = ExtendedThinkingTrace.create("To be deleted")
        trace.complete()

        store.save_extended_thinking_trace(
            trace_id=trace.trace_id,
            conversation_id="conv-del",
            message_id="msg-del",
            prompt=trace.prompt,
            started_at=trace.started_at,
            completed_at=trace.completed_at,
            trace_json=json.dumps(trace.to_dict()),
            summary=trace.summary(),
            decision="respond",
            final_confidence=0.8,
        )

        # Verify exists
        assert store.get_extended_thinking_trace(trace.trace_id) is not None

        # Delete
        deleted = store.delete_extended_thinking_trace(trace.trace_id)
        assert deleted is True

        # Verify gone
        assert store.get_extended_thinking_trace(trace.trace_id) is None

        # Delete non-existent returns False
        assert store.delete_extended_thinking_trace("non-existent") is False
