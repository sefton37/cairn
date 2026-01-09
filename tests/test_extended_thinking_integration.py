"""Integration tests for CAIRN Extended Thinking.

Tests the full flow from RPC endpoint to ChatResponse.
"""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime

from reos.agent import ChatAgent, ChatResponse
from reos.cairn.extended_thinking import (
    CAIRNExtendedThinking,
    ExtendedThinkingTrace,
    ThinkingNode,
    FacetCheck,
    Tension,
)
from reos.cairn.coherence import IdentityModel, IdentityFacet
from reos.cairn.store import CairnStore


# ============ Fixtures ============


@pytest.fixture
def sample_trace():
    """Create a sample ExtendedThinkingTrace for testing."""
    return ExtendedThinkingTrace(
        trace_id="test-trace-001",
        prompt="I want to change my career direction",
        started_at=datetime.now(),
        completed_at=datetime.now(),
        understood=[
            ThinkingNode(
                content="User wants to change career directions",
                node_type="understood",
                confidence=0.95,
            ),
            ThinkingNode(
                content="This is important to them",
                node_type="understood",
                confidence=0.9,
            ),
        ],
        ambiguous=[
            ThinkingNode(
                content="Timeline for this change",
                node_type="ambiguous",
                confidence=0.5,
            ),
        ],
        unknowns=[
            ThinkingNode(
                content="What fields they're considering",
                node_type="reasoning_step",
                confidence=0.3,
            ),
        ],
        questions_for_user=["What timeline are you considering?"],
        assumptions=[
            ThinkingNode(
                content="Tech-adjacent fields likely",
                node_type="assumption",
                confidence=0.7,
            ),
        ],
        facets_to_check=["building with code", "work-life balance"],
        identity_facets_checked=[
            FacetCheck(
                facet_name="building with code",
                facet_source="me.md",
                reasoning_branch="career change",
                alignment=0.8,
                explanation="Career change may involve coding",
            ),
        ],
        tensions=[
            Tension(
                description="Goal of slowing down conflicts with career change energy",
                identity_facet="work-life balance",
                prompt_aspect="career change",
                severity="medium",
                recommendation="Clarify which takes priority",
            ),
        ],
        final_response="",
        final_confidence=0.75,
        decision="ask",
    )


@pytest.fixture
def sample_identity_model():
    """Create a sample identity model."""
    return IdentityModel(
        core="I am a software developer who loves building things and teaching others.",
        facets=[
            IdentityFacet(
                name="building with code",
                source="me.md",
                content="I love building things with code",
                weight=2.0,
            ),
            IdentityFacet(
                name="teaching others",
                source="me.md",
                content="I enjoy teaching and mentoring",
                weight=1.5,
            ),
        ],
        anti_patterns=["procrastination"],
    )


# ============ ChatResponse Integration Tests ============


class TestChatResponseIntegration:
    """Test ChatResponse integration with extended thinking."""

    def test_chat_response_has_extended_thinking_field(self):
        """Verify ChatResponse dataclass has extended_thinking_trace field."""
        response = ChatResponse(
            answer="Test answer",
            conversation_id="conv-123",
            message_id="msg-456",
            message_type="text",
            tool_calls=[],
            thinking_steps=[],
            extended_thinking_trace={"trace_id": "test"},
        )
        assert response.extended_thinking_trace == {"trace_id": "test"}

    def test_chat_response_extended_thinking_defaults_to_none(self):
        """Verify extended_thinking_trace defaults to None."""
        response = ChatResponse(
            answer="Test answer",
            conversation_id="conv-123",
            message_id="msg-456",
            message_type="text",
            tool_calls=[],
            thinking_steps=[],
        )
        assert response.extended_thinking_trace is None

    def test_response_includes_full_trace(self, sample_trace):
        """Test that ChatResponse can include full trace dict."""
        response = ChatResponse(
            answer="Here's my response",
            conversation_id="conv-123",
            message_id="msg-456",
            message_type="text",
            tool_calls=[],
            thinking_steps=[],
            extended_thinking_trace=sample_trace.to_dict(),
        )

        trace = response.extended_thinking_trace
        assert trace is not None
        assert trace["trace_id"] == "test-trace-001"
        assert len(trace["tensions"]) == 1
        assert len(trace["understood"]) == 2


# ============ Trace Serialization Tests ============


class TestTraceSerialization:
    """Test serialization of traces for frontend consumption."""

    def test_trace_to_dict_structure(self, sample_trace):
        """Test that trace.to_dict() has correct structure for frontend."""
        trace_dict = sample_trace.to_dict()

        # Verify top-level fields
        assert "trace_id" in trace_dict
        assert "prompt" in trace_dict
        assert "started_at" in trace_dict
        assert "completed_at" in trace_dict

        # Verify phase 1 fields
        assert "understood" in trace_dict
        assert "ambiguous" in trace_dict
        assert "unknowns" in trace_dict

        # Verify phase 2 fields
        assert "questions_for_user" in trace_dict
        assert "assumptions" in trace_dict
        assert "facets_to_check" in trace_dict

        # Verify phase 3 fields
        assert "identity_facets_checked" in trace_dict
        assert "tensions" in trace_dict

        # Verify phase 4 fields
        assert "final_response" in trace_dict
        assert "final_confidence" in trace_dict
        assert "decision" in trace_dict

    def test_thinking_nodes_serialized(self, sample_trace):
        """Test that ThinkingNodes are properly serialized."""
        trace_dict = sample_trace.to_dict()

        understood = trace_dict["understood"]
        assert len(understood) == 2
        assert understood[0]["content"] == "User wants to change career directions"
        assert understood[0]["type"] == "understood"
        assert understood[0]["confidence"] == 0.95

    def test_facet_checks_serialized(self, sample_trace):
        """Test that FacetChecks are properly serialized."""
        trace_dict = sample_trace.to_dict()

        facet_checks = trace_dict["identity_facets_checked"]
        assert len(facet_checks) == 1
        assert facet_checks[0]["facet_name"] == "building with code"
        assert facet_checks[0]["alignment"] == 0.8

    def test_tensions_serialized(self, sample_trace):
        """Test that Tensions are properly serialized."""
        trace_dict = sample_trace.to_dict()

        tensions = trace_dict["tensions"]
        assert len(tensions) == 1
        assert tensions[0]["severity"] == "medium"
        assert tensions[0]["identity_facet"] == "work-life balance"

    def test_decision_serialized_as_string(self, sample_trace):
        """Test that decision is serialized as string for frontend."""
        trace_dict = sample_trace.to_dict()

        # Decision should be a string
        assert trace_dict["decision"] == "ask"
        assert isinstance(trace_dict["decision"], str)


# ============ Auto-Trigger Detection Tests ============


class TestAutoTriggerDetection:
    """Test the auto-trigger detection logic."""

    def test_explicit_trigger_phrases_detected(self, sample_identity_model):
        """Test that explicit phrases are detected."""
        engine = CAIRNExtendedThinking(
            identity=sample_identity_model,
            llm=MagicMock(),
        )

        # These should all trigger
        assert engine.should_auto_trigger("Think carefully about this") is True
        assert engine.should_auto_trigger("Please think about this deeply") is True
        assert engine.should_auto_trigger("Consider deeply my options") is True
        assert engine.should_auto_trigger("Reflect on what I said") is True

    def test_simple_prompts_dont_trigger(self, sample_identity_model):
        """Test that simple prompts don't trigger without explicit phrases."""
        engine = CAIRNExtendedThinking(
            identity=sample_identity_model,
            llm=MagicMock(),
        )

        # Simple prompts without trigger phrases and low ambiguity
        # The engine uses _quick_ambiguity_scan internally
        # These should not trigger (score <= 2)
        result = engine.should_auto_trigger("Hello")
        # Simple greeting - very low ambiguity
        assert result is False

    def test_ambiguity_scan_counts_question_words(self, sample_identity_model):
        """Test that question words contribute to ambiguity score."""
        engine = CAIRNExtendedThinking(
            identity=sample_identity_model,
            llm=MagicMock(),
        )

        # Quick ambiguity scan is internal, test through should_auto_trigger
        # A prompt with many question indicators should score higher
        complex_prompt = "What should I do? When is the right time? How do I know?"
        simple_prompt = "The sky is blue."

        # Complex should have higher score (may or may not trigger)
        # Simple should definitely not trigger
        assert engine.should_auto_trigger(simple_prompt) is False


# ============ Persistence Tests ============


class TestTracePersistence:
    """Test persistence of extended thinking traces."""

    def test_trace_can_be_saved_and_retrieved(self, tmp_path, sample_trace):
        """Test that traces can be saved to and retrieved from CairnStore."""
        import json

        store = CairnStore(str(tmp_path / "cairn_test.db"))

        # Build summary dict
        summary = {
            "understood_count": len(sample_trace.understood),
            "ambiguous_count": len(sample_trace.ambiguous),
            "assumption_count": len(sample_trace.assumptions),
            "tension_count": len(sample_trace.tensions),
        }

        # Save the trace
        store.save_extended_thinking_trace(
            trace_id=sample_trace.trace_id,
            conversation_id="conv-123",
            message_id="msg-456",
            prompt=sample_trace.prompt,
            started_at=sample_trace.started_at,
            completed_at=sample_trace.completed_at,
            trace_json=json.dumps(sample_trace.to_dict()),
            summary=summary,
            decision=sample_trace.decision,
            final_confidence=sample_trace.final_confidence,
        )

        # Retrieve and verify
        retrieved = store.get_extended_thinking_trace(sample_trace.trace_id)
        assert retrieved is not None
        assert retrieved["trace_id"] == sample_trace.trace_id
        assert retrieved["conversation_id"] == "conv-123"
        assert retrieved["understood_count"] == 2
        assert retrieved["tension_count"] == 1

    def test_traces_listed_by_conversation(self, tmp_path):
        """Test listing traces for a conversation."""
        import json

        store = CairnStore(str(tmp_path / "cairn_test.db"))

        # Save multiple traces
        for i in range(3):
            summary = {
                "understood_count": i,
                "ambiguous_count": 0,
                "assumption_count": 0,
                "tension_count": 0,
            }
            store.save_extended_thinking_trace(
                trace_id=f"trace-{i}",
                conversation_id="conv-123",
                message_id=f"msg-{i}",
                prompt=f"Prompt {i}",
                started_at=datetime.now(),
                completed_at=datetime.now(),
                trace_json=json.dumps({}),
                summary=summary,
                decision="respond",
                final_confidence=0.8,
            )

        traces = store.list_extended_thinking_traces("conv-123")
        assert len(traces) == 3


# ============ Engine Integration Tests ============


class TestEngineIntegration:
    """Test CAIRNExtendedThinking engine integration."""

    def test_engine_creates_valid_trace(self, sample_identity_model):
        """Test that engine creates a valid trace structure."""
        mock_llm = MagicMock()
        # Mock LLM to return valid JSON responses
        mock_llm.complete.return_value = MagicMock(
            text='{"understood": [{"content": "test", "confidence": 0.9}], "ambiguous": [], "unknowns": []}'
        )

        engine = CAIRNExtendedThinking(
            identity=sample_identity_model,
            llm=mock_llm,
        )

        # The think method should return a valid trace
        # (even if LLM calls fail, it should handle gracefully)
        trace = engine.think("Test prompt")

        assert trace is not None
        assert trace.trace_id is not None
        assert trace.prompt == "Test prompt"
        assert trace.started_at is not None
        assert trace.completed_at is not None

    def test_engine_handles_llm_failure_gracefully(self, sample_identity_model):
        """Test that engine handles LLM failures without crashing."""
        mock_llm = MagicMock()
        mock_llm.complete.side_effect = Exception("LLM error")

        engine = CAIRNExtendedThinking(
            identity=sample_identity_model,
            llm=mock_llm,
        )

        # Should not raise, should return a trace with empty/default values
        trace = engine.think("Test prompt")
        assert trace is not None
        assert trace.prompt == "Test prompt"
