"""CAIRN Extended Thinking Engine.

Kernel: "Verify understanding, decompose, or surface to user. Show your work."

This module implements user-triggered extended thinking mode that makes
CAIRN's reasoning process visible and transparent. When activated, it:
1. Shows what was understood clearly
2. Shows what was ambiguous or assumed
3. Checks understanding against user identity (The Play)
4. Surfaces tensions or conflicts with stated identity
5. Returns a complete trace of the reasoning process

The architecture follows a 4-phase process:
- Comprehension Check: What do I understand? What's ambiguous?
- Decomposition: Break unknowns into questions, assumptions, facets to check
- Coherence Verification: Does this align with who they are becoming?
- Response + Trace: Final decision with full audit trail
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from cairn.cairn.coherence import IdentityModel
    from cairn.providers import LLMProvider

logger = logging.getLogger(__name__)


def _parse_llm_json(text: str) -> Any:
    """Parse JSON from an LLM response, stripping markdown code fences if present."""
    text = text.strip()
    # Strip ```json ... ``` or ``` ... ``` fences
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text.strip())


# =============================================================================
# Type Aliases
# =============================================================================

NodeType = Literal[
    "understood",       # Clearly understood from prompt
    "ambiguous",        # Multiple interpretations possible
    "assumption",       # Inference made without explicit info
    "identity_check",   # Facet of identity checked
    "tension",          # Conflict with identity
    "reasoning_step",   # Logical step in reasoning
]

DecisionType = Literal["respond", "ask", "defer"]


# =============================================================================
# Data Structures
# =============================================================================


@dataclass
class ThinkingNode:
    """A single node in the extended thinking tree.

    Represents one piece of understanding, ambiguity, or assumption
    in the reasoning process. Nodes can have children for decomposition.

    Attributes:
        content: The text content of this node
        node_type: Category of this node (understood, ambiguous, etc.)
        confidence: How confident we are (0.0 - 1.0)
        children: Child nodes if this was decomposed further
    """

    content: str
    node_type: NodeType
    confidence: float = 1.0
    children: list["ThinkingNode"] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "content": self.content,
            "type": self.node_type,
            "confidence": self.confidence,
            "children": [c.to_dict() for c in self.children],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ThinkingNode:
        return cls(
            content=data["content"],
            node_type=data["type"],
            confidence=data.get("confidence", 1.0),
            children=[cls.from_dict(c) for c in data.get("children", [])],
        )


@dataclass
class FacetCheck:
    """Result of checking a reasoning branch against an identity facet.

    When we verify coherence, we check various reasoning branches against
    the user's identity facets from The Play. This captures those checks.

    Attributes:
        facet_name: Which facet from The Play (e.g., "values", "goals")
        facet_source: Where it came from (me.md, Act, Scene)
        reasoning_branch: What we were checking
        alignment: -1.0 (conflicts) to 1.0 (aligns)
        explanation: Why this alignment score
    """

    facet_name: str
    facet_source: str
    reasoning_branch: str
    alignment: float
    explanation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "facet_name": self.facet_name,
            "facet_source": self.facet_source,
            "reasoning_branch": self.reasoning_branch,
            "alignment": self.alignment,
            "explanation": self.explanation,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FacetCheck:
        return cls(
            facet_name=data["facet_name"],
            facet_source=data["facet_source"],
            reasoning_branch=data["reasoning_branch"],
            alignment=data.get("alignment", 0.0),
            explanation=data.get("explanation", ""),
        )


@dataclass
class Tension:
    """A detected tension between prompt and identity.

    When we find conflicts between what the user is asking and their
    stated identity/goals, we surface these as tensions.

    Attributes:
        description: What the tension is
        identity_facet: Which part of identity it conflicts with
        prompt_aspect: Which part of the prompt creates the conflict
        severity: low, medium, or high
        recommendation: How to resolve this tension
    """

    description: str
    identity_facet: str
    prompt_aspect: str
    severity: Literal["low", "medium", "high"]
    recommendation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "description": self.description,
            "identity_facet": self.identity_facet,
            "prompt_aspect": self.prompt_aspect,
            "severity": self.severity,
            "recommendation": self.recommendation,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Tension:
        return cls(
            description=data["description"],
            identity_facet=data["identity_facet"],
            prompt_aspect=data["prompt_aspect"],
            severity=data.get("severity", "low"),
            recommendation=data.get("recommendation", ""),
        )


@dataclass
class ExtendedThinkingTrace:
    """Complete trace of extended thinking on a prompt.

    This is the main output of the extended thinking process. It captures
    everything CAIRN thought about while processing a prompt, organized
    by the 4 phases of the thinking process.

    Attributes:
        trace_id: Unique identifier for this trace
        prompt: The original user prompt
        started_at: When thinking began
        completed_at: When thinking finished

        # Phase 1: Comprehension
        understood: Things clearly understood from prompt
        ambiguous: Things with multiple interpretations
        unknowns: Things we don't know but need to

        # Phase 2: Decomposition
        questions_for_user: Questions we should ask
        assumptions: Inferences we're making
        facets_to_check: Identity facets to verify against

        # Phase 3: Coherence
        identity_facets_checked: Results of coherence checks
        tensions: Detected conflicts with identity

        # Phase 4: Result
        final_response: The response we're giving
        final_confidence: Overall confidence (0.0 - 1.0)
        decision: Whether to respond, ask, or defer
    """

    trace_id: str
    prompt: str
    started_at: datetime
    completed_at: datetime | None = None

    # Phase 1: Comprehension
    understood: list[ThinkingNode] = field(default_factory=list)
    ambiguous: list[ThinkingNode] = field(default_factory=list)
    unknowns: list[ThinkingNode] = field(default_factory=list)

    # Phase 2: Decomposition
    questions_for_user: list[str] = field(default_factory=list)
    assumptions: list[ThinkingNode] = field(default_factory=list)
    facets_to_check: list[str] = field(default_factory=list)

    # Phase 3: Coherence
    identity_facets_checked: list[FacetCheck] = field(default_factory=list)
    tensions: list[Tension] = field(default_factory=list)

    # Phase 4: Result
    final_response: str = ""
    final_confidence: float = 0.0
    decision: DecisionType = "respond"

    @staticmethod
    def create(prompt: str) -> ExtendedThinkingTrace:
        """Create a new trace with generated ID."""
        return ExtendedThinkingTrace(
            trace_id=f"trace-{uuid.uuid4().hex[:12]}",
            prompt=prompt,
            started_at=datetime.now(timezone.utc),
        )

    def complete(self) -> None:
        """Mark the trace as complete."""
        self.completed_at = datetime.now(timezone.utc)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "prompt": self.prompt,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            # Phase 1
            "understood": [n.to_dict() for n in self.understood],
            "ambiguous": [n.to_dict() for n in self.ambiguous],
            "unknowns": [n.to_dict() for n in self.unknowns],
            # Phase 2
            "questions_for_user": self.questions_for_user,
            "assumptions": [n.to_dict() for n in self.assumptions],
            "facets_to_check": self.facets_to_check,
            # Phase 3
            "identity_facets_checked": [f.to_dict() for f in self.identity_facets_checked],
            "tensions": [t.to_dict() for t in self.tensions],
            # Phase 4
            "final_response": self.final_response,
            "final_confidence": self.final_confidence,
            "decision": self.decision,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExtendedThinkingTrace:
        return cls(
            trace_id=data["trace_id"],
            prompt=data["prompt"],
            started_at=datetime.fromisoformat(data["started_at"]),
            completed_at=(
                datetime.fromisoformat(data["completed_at"])
                if data.get("completed_at")
                else None
            ),
            # Phase 1
            understood=[ThinkingNode.from_dict(n) for n in data.get("understood", [])],
            ambiguous=[ThinkingNode.from_dict(n) for n in data.get("ambiguous", [])],
            unknowns=[ThinkingNode.from_dict(n) for n in data.get("unknowns", [])],
            # Phase 2
            questions_for_user=data.get("questions_for_user", []),
            assumptions=[ThinkingNode.from_dict(n) for n in data.get("assumptions", [])],
            facets_to_check=data.get("facets_to_check", []),
            # Phase 3
            identity_facets_checked=[
                FacetCheck.from_dict(f) for f in data.get("identity_facets_checked", [])
            ],
            tensions=[Tension.from_dict(t) for t in data.get("tensions", [])],
            # Phase 4
            final_response=data.get("final_response", ""),
            final_confidence=data.get("final_confidence", 0.0),
            decision=data.get("decision", "respond"),
        )

    def summary(self) -> dict[str, int]:
        """Get summary counts for quick display."""
        return {
            "understood_count": len(self.understood),
            "ambiguous_count": len(self.ambiguous),
            "assumption_count": len(self.assumptions),
            "tension_count": len(self.tensions),
            "questions_count": len(self.questions_for_user),
        }

    def format_for_display(self) -> str:
        """Format trace for text display (e.g., in chat)."""
        parts = []

        if self.understood:
            parts.append("**Understood:**")
            for node in self.understood:
                parts.append(f"  - {node.content}")

        if self.assumptions:
            parts.append("\n**Assumptions I made:**")
            for node in self.assumptions:
                confidence_pct = int(node.confidence * 100)
                parts.append(f"  - {node.content} ({confidence_pct}%)")

        if self.identity_facets_checked:
            parts.append("\n**Checked against your identity:**")
            for check in self.identity_facets_checked:
                align_str = "aligns" if check.alignment > 0 else "conflicts"
                parts.append(
                    f"  - \"{check.facet_name}\" - {align_str} ({check.alignment:.1f})"
                )

        if self.tensions:
            parts.append("\n**Tensions detected:**")
            for tension in self.tensions:
                parts.append(f"  - {tension.description}")
                parts.append(f"    Recommendation: {tension.recommendation}")

        if self.questions_for_user:
            parts.append("\n**Questions for you:**")
            for q in self.questions_for_user:
                parts.append(f"  - {q}")

        return "\n".join(parts)


# =============================================================================
# Extended Thinking Engine
# =============================================================================


class CAIRNExtendedThinking:
    """Extended thinking engine for CAIRN.

    Implements the kernel: "Verify understanding, decompose, or surface to user."

    This engine runs a 4-phase thinking process on prompts:
    1. Comprehension Check - What do I understand clearly vs. not?
    2. Decomposition - Break unknowns into questions, assumptions, facets
    3. Coherence Verification - Check against user's identity model
    4. Decision - Respond, ask for clarification, or defer

    Attributes:
        identity: The user's identity model from The Play
        llm: LLM provider for analysis
        max_depth: Maximum recursion depth for decomposition
    """

    # Phrases that trigger extended thinking
    TRIGGER_PHRASES = [
        "think carefully",
        "think about this",
        "consider deeply",
        "reflect on",
        "reason through",
        "analyze this",
    ]

    def __init__(
        self,
        identity: "IdentityModel",
        llm: "LLMProvider",
        max_depth: int = 3,
    ):
        self.identity = identity
        self.llm = llm
        self.max_depth = max_depth

    def should_auto_trigger(self, prompt: str) -> bool:
        """Decide if extended thinking should auto-trigger.

        Auto-enables when:
        - Prompt contains trigger phrases
        - Prompt contains >2 ambiguous elements (quick heuristic)
        - Prompt touches identity (goals, values, life decisions)

        Args:
            prompt: The user's prompt

        Returns:
            True if extended thinking should run automatically
        """
        prompt_lower = prompt.lower()

        # Explicit trigger phrases
        if any(t in prompt_lower for t in self.TRIGGER_PHRASES):
            logger.debug("Extended thinking triggered by phrase")
            return True

        # Quick ambiguity scan
        ambiguity_score = self._quick_ambiguity_scan(prompt)
        if ambiguity_score > 2:
            logger.debug("Extended thinking triggered by ambiguity (score=%d)", ambiguity_score)
            return True

        # Identity-related prompts
        identity_keywords = [
            "should i", "what should", "my goal", "my life",
            "career", "decision", "values", "purpose", "meaning",
            "future", "direction", "priority", "important to me",
        ]
        if sum(1 for kw in identity_keywords if kw in prompt_lower) >= 2:
            logger.debug("Extended thinking triggered by identity keywords")
            return True

        return False

    def _quick_ambiguity_scan(self, prompt: str) -> int:
        """Quick heuristic to estimate ambiguity in a prompt.

        Counts indicators of ambiguity without calling LLM.

        Returns:
            Estimated ambiguity score (0-10)
        """
        score = 0
        prompt_lower = prompt.lower()

        # Vague terms
        vague_terms = ["maybe", "perhaps", "might", "could", "sort of", "kind of"]
        score += sum(1 for t in vague_terms if t in prompt_lower)

        # Open-ended question words
        open_questions = ["what if", "how might", "should i", "would you"]
        score += sum(1 for q in open_questions if q in prompt_lower)

        # Multiple things mentioned (potential for ambiguity)
        if " and " in prompt_lower:
            score += prompt_lower.count(" and ")

        # Questions about choices
        if " or " in prompt_lower:
            score += prompt_lower.count(" or ")

        # Pronouns without clear referents
        if len(prompt.split()) > 20:  # Longer prompts
            pronouns = ["it", "this", "that", "they"]
            score += min(2, sum(1 for p in pronouns if f" {p} " in prompt_lower))

        return min(score, 10)  # Cap at 10

    def think(self, prompt: str) -> ExtendedThinkingTrace:
        """Run extended thinking on a prompt.

        Executes the 4-phase thinking process and returns a complete trace.

        Args:
            prompt: The user's prompt to think about

        Returns:
            ExtendedThinkingTrace with full reasoning trace
        """
        trace = ExtendedThinkingTrace.create(prompt)

        try:
            # Phase 1: Comprehension Check
            logger.debug("Extended thinking Phase 1: Comprehension Check")
            trace.understood, trace.ambiguous, trace.unknowns = (
                self._comprehension_check(prompt)
            )

            # Phase 2: Decomposition
            logger.debug("Extended thinking Phase 2: Decomposition")
            trace.questions_for_user, trace.assumptions, trace.facets_to_check = (
                self._decompose(trace.ambiguous, trace.unknowns)
            )

            # Phase 3: Coherence Verification
            logger.debug("Extended thinking Phase 3: Coherence Verification")
            trace.identity_facets_checked, trace.tensions = (
                self._verify_coherence(trace.understood, trace.assumptions)
            )

            # Phase 4: Decision
            logger.debug("Extended thinking Phase 4: Decision")
            trace.decision, trace.final_confidence = self._make_decision(trace)

        except Exception as e:
            logger.error("Extended thinking failed: %s", e, exc_info=True)
            # Return partial trace with error
            trace.decision = "respond"
            trace.final_confidence = 0.5

        trace.complete()
        return trace

    def _comprehension_check(
        self, prompt: str
    ) -> tuple[list[ThinkingNode], list[ThinkingNode], list[ThinkingNode]]:
        """Phase 1: What do we understand clearly vs. not?

        Uses LLM to analyze the prompt and categorize components into:
        - Understood: Clearly stated, unambiguous
        - Ambiguous: Multiple interpretations possible
        - Unknown: Information we need but don't have

        Args:
            prompt: The user's prompt

        Returns:
            Tuple of (understood, ambiguous, unknowns) lists
        """
        system_prompt = """You are analyzing a user's prompt to understand what is clear and what is ambiguous.

Categorize each component of the prompt into:
1. UNDERSTOOD - Clearly stated, unambiguous parts
2. AMBIGUOUS - Parts with multiple possible interpretations
3. UNKNOWN - Information that would be needed but isn't provided

Respond with ONLY a JSON object:
{
  "understood": [
    {"content": "what you clearly understand", "confidence": 0.9}
  ],
  "ambiguous": [
    {"content": "what has multiple interpretations", "interpretations": ["option1", "option2"]}
  ],
  "unknowns": [
    {"content": "what information is missing"}
  ]
}"""

        user_prompt = f"""Analyze this prompt and identify what is understood, ambiguous, or unknown:

PROMPT: {prompt}

Be specific about each component."""

        try:
            response = self.llm.chat_json(
                system=system_prompt,
                user=user_prompt,
                timeout_seconds=20.0,
            )

            data = _parse_llm_json(response)

            understood = [
                ThinkingNode(
                    content=item.get("content", ""),
                    node_type="understood",
                    confidence=item.get("confidence", 0.9),
                )
                for item in data.get("understood", [])
            ]

            ambiguous = [
                ThinkingNode(
                    content=item.get("content", ""),
                    node_type="ambiguous",
                    confidence=0.5,  # Ambiguous items get 50% confidence
                    children=[
                        ThinkingNode(content=interp, node_type="reasoning_step", confidence=0.5)
                        for interp in item.get("interpretations", [])
                    ],
                )
                for item in data.get("ambiguous", [])
            ]

            unknowns = [
                ThinkingNode(
                    content=item.get("content", item) if isinstance(item, dict) else str(item),
                    node_type="reasoning_step",
                    confidence=0.0,
                )
                for item in data.get("unknowns", [])
            ]

            return understood, ambiguous, unknowns

        except Exception as e:
            logger.warning("Comprehension check failed: %s", e)
            # Fallback: treat entire prompt as understood
            return (
                [ThinkingNode(content=prompt, node_type="understood", confidence=0.7)],
                [],
                [],
            )

    def _decompose(
        self,
        ambiguous: list[ThinkingNode],
        unknowns: list[ThinkingNode],
    ) -> tuple[list[str], list[ThinkingNode], list[str]]:
        """Phase 2: Break down unknowns into actionable items.

        For each ambiguous or unknown element, decide:
        - Should we ask the user? (question)
        - Should we make an assumption? (with disclosure)
        - Should we check against identity? (facet to check)

        Args:
            ambiguous: Ambiguous elements from Phase 1
            unknowns: Unknown elements from Phase 1

        Returns:
            Tuple of (questions, assumptions, facets_to_check)
        """
        if not ambiguous and not unknowns:
            return [], [], []

        # Format input for LLM
        ambiguous_text = "\n".join(f"- {n.content}" for n in ambiguous)
        unknowns_text = "\n".join(f"- {n.content}" for n in unknowns)

        # Get identity facet names for reference
        facet_names = list({f.name for f in self.identity.facets})

        system_prompt = """You are decomposing ambiguities and unknowns into actionable items.

For each item, decide the best approach:
1. ASK - A question we should ask the user to clarify
2. ASSUME - An assumption we should make (with disclosure)
3. CHECK_IDENTITY - A facet of identity to verify against

Available identity facets: """ + ", ".join(facet_names) + """

Respond with ONLY a JSON object:
{
  "questions": ["specific question to ask user"],
  "assumptions": [
    {"content": "what we're assuming", "confidence": 0.7, "reason": "why this assumption"}
  ],
  "facets_to_check": ["facet_name1", "facet_name2"]
}"""

        user_prompt = f"""Decompose these ambiguities and unknowns:

AMBIGUOUS:
{ambiguous_text or "(none)"}

UNKNOWN:
{unknowns_text or "(none)"}

Decide what to ask, assume, or check against identity."""

        try:
            response = self.llm.chat_json(
                system=system_prompt,
                user=user_prompt,
                timeout_seconds=15.0,
            )

            data = _parse_llm_json(response)

            questions = data.get("questions", [])

            assumptions = [
                ThinkingNode(
                    content=item.get("content", ""),
                    node_type="assumption",
                    confidence=item.get("confidence", 0.6),
                )
                for item in data.get("assumptions", [])
            ]

            facets_to_check = data.get("facets_to_check", [])

            return questions, assumptions, facets_to_check

        except Exception as e:
            logger.warning("Decomposition failed: %s", e)
            # Fallback: convert unknowns to questions
            questions = [f"Could you clarify: {n.content}?" for n in unknowns[:3]]
            return questions, [], []

    def _verify_coherence(
        self,
        understood: list[ThinkingNode],
        assumptions: list[ThinkingNode],
    ) -> tuple[list[FacetCheck], list[Tension]]:
        """Phase 3: Check reasoning against identity model.

        Verify that what we understand and assume aligns with the user's
        identity as expressed in The Play.

        Args:
            understood: Things we clearly understood
            assumptions: Assumptions we're making

        Returns:
            Tuple of (facet_checks, tensions)
        """
        from cairn.cairn.coherence import AttentionDemand, CoherenceVerifier

        facet_checks: list[FacetCheck] = []
        tensions: list[Tension] = []

        # Create verifier
        verifier = CoherenceVerifier(
            identity=self.identity,
            llm=self.llm,
            max_depth=2,
        )

        # Check each understood and assumed element
        all_nodes = understood + assumptions
        for node in all_nodes[:5]:  # Limit to 5 to avoid too many LLM calls
            demand = AttentionDemand.create(
                source="extended_thinking",
                content=node.content,
                urgency=5,
            )

            try:
                result = verifier.verify(demand)

                # Record facet checks
                for check in result.checks:
                    facet_checks.append(
                        FacetCheck(
                            facet_name=check.facet_checked,
                            facet_source="identity",
                            reasoning_branch=node.content,
                            alignment=check.alignment,
                            explanation=check.reasoning,
                        )
                    )

                # Detect tensions (negative alignment)
                if result.overall_score < -0.3:
                    tensions.append(
                        Tension(
                            description=(
                                f"'{node.content[:50]}...' may conflict with your identity"
                            ),
                            identity_facet=result.checks[0].facet_checked if result.checks else "core",
                            prompt_aspect=node.content[:100],
                            severity="medium" if result.overall_score < -0.5 else "low",
                            recommendation=(
                                "Consider whether this aligns with your stated goals and values"
                            ),
                        )
                    )

            except Exception as e:
                logger.warning("Coherence check failed for '%s': %s", node.content[:30], e)

        return facet_checks, tensions

    def _make_decision(
        self, trace: ExtendedThinkingTrace
    ) -> tuple[DecisionType, float]:
        """Phase 4: Decide whether to respond, ask, or defer.

        Based on the trace, decide the appropriate action:
        - respond: We have enough confidence to proceed
        - ask: We need clarification from the user
        - defer: This requires more thought or is outside our scope

        Args:
            trace: The thinking trace so far

        Returns:
            Tuple of (decision, final_confidence)
        """
        # Calculate overall confidence
        confidences = []

        # Weight understood items
        for node in trace.understood:
            confidences.append(node.confidence)

        # Weight assumptions lower
        for node in trace.assumptions:
            confidences.append(node.confidence * 0.7)

        # Penalize for tensions
        tension_penalty = len(trace.tensions) * 0.1

        if confidences:
            avg_confidence = sum(confidences) / len(confidences)
            final_confidence = max(0.0, min(1.0, avg_confidence - tension_penalty))
        else:
            final_confidence = 0.5

        # Decision logic
        if trace.questions_for_user and len(trace.questions_for_user) > len(trace.understood):
            # More questions than understanding - ask
            decision: DecisionType = "ask"
        elif final_confidence < 0.4:
            # Low confidence - ask
            decision = "ask"
        elif len(trace.tensions) > 2:
            # Many tensions - defer for human judgment
            decision = "defer"
        elif any(t.severity == "high" for t in trace.tensions):
            # High severity tension - ask
            decision = "ask"
        else:
            # Proceed with response
            decision = "respond"

        return decision, final_confidence

    def should_ask(
        self, assumption: ThinkingNode, trace: ExtendedThinkingTrace
    ) -> bool:
        """Decide if we should ask about a specific assumption.

        Decision logic:
        - High stakes (affects identity) → ASK
        - Prior signal exists in The Play → ASSUME with disclosure
        - Low confidence (<0.6) → ASK
        - Recoverable if wrong → ASSUME with disclosure
        - Default → ASK

        Args:
            assumption: The assumption to evaluate
            trace: Current thinking trace for context

        Returns:
            True if we should ask, False if we can assume
        """
        # Low confidence - always ask
        if assumption.confidence < 0.6:
            return True

        # Check if this affects identity
        identity_keywords = ["goal", "value", "belief", "principle", "priority"]
        content_lower = assumption.content.lower()
        if any(kw in content_lower for kw in identity_keywords):
            return True

        # Check for prior signal in identity
        relevant_facets = self.identity.get_relevant_facets(
            assumption.content.split()[:5]
        )
        if relevant_facets and any(f.weight >= 1.5 for f in relevant_facets):
            # Strong prior signal - can assume
            return False

        # Check if recoverable (heuristic: action words suggest less recoverable)
        action_words = ["delete", "remove", "change", "cancel", "stop", "start"]
        if any(w in content_lower for w in action_words):
            return True

        # Default to asking
        return True
