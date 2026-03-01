"""Certainty wrapper for anti-hallucination safeguards.

Ensures LLM outputs are grounded in evidence and explicitly declares
uncertainty when evidence is lacking.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class EvidenceType(Enum):
    """Types of evidence that can support a claim."""

    SYSTEM_STATE = "system_state"  # From SteadyState (static)
    TOOL_OUTPUT = "tool_output"  # From tool execution
    USER_INPUT = "user_input"  # From user's message
    INFERENCE = "inference"  # Logical deduction from evidence
    NONE = "none"  # No evidence available


class UncertaintyReason(Enum):
    """Reasons for uncertainty in a claim."""

    NO_DATA = "no_data"  # No evidence available
    STALE_DATA = "stale_data"  # Evidence is too old
    CONFLICTING_DATA = "conflicting_data"  # Multiple conflicting sources
    INFERENCE_ONLY = "inference_only"  # Based on inference, not direct evidence
    PARTIAL_MATCH = "partial_match"  # Evidence partially supports claim
    TOOL_NEEDED = "tool_needed"  # Need to run a tool to verify


@dataclass
class Evidence:
    """Evidence supporting a factual claim."""

    evidence_type: EvidenceType
    source: str  # e.g., "SteadyState.hostname", "linux_containers"
    value: Any  # The actual evidence value
    timestamp: datetime | None = None  # When evidence was collected
    confidence: float = 1.0  # How certain is this evidence (0-1)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.evidence_type.value,
            "source": self.source,
            "value": str(self.value),
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "confidence": self.confidence,
        }


@dataclass
class Fact:
    """A factual claim with supporting evidence."""

    claim: str
    evidence: Evidence
    verified: bool = True  # Was this verified against evidence?

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim": self.claim,
            "evidence": self.evidence.to_dict(),
            "verified": self.verified,
        }


@dataclass
class Uncertainty:
    """An uncertainty declaration about a claim or topic."""

    claim: str  # What we're uncertain about
    reason: UncertaintyReason
    suggestion: str | None = None  # What could resolve the uncertainty
    confidence: float = 0.0  # How confident despite uncertainty (0-1)

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim": self.claim,
            "reason": self.reason.value,
            "suggestion": self.suggestion,
            "confidence": self.confidence,
        }


@dataclass
class CertainResponse:
    """A response with explicit certainty tracking.

    This wraps LLM responses with metadata about:
    - What facts are stated and their evidence
    - What uncertainties exist
    - Overall confidence in the response
    """

    answer: str  # The actual response text
    facts: list[Fact] = field(default_factory=list)
    uncertainties: list[Uncertainty] = field(default_factory=list)
    overall_confidence: float = 1.0
    evidence_summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "answer": self.answer,
            "facts": [f.to_dict() for f in self.facts],
            "uncertainties": [u.to_dict() for u in self.uncertainties],
            "overall_confidence": self.overall_confidence,
            "evidence_summary": self.evidence_summary,
        }

    def has_uncertainties(self) -> bool:
        return len(self.uncertainties) > 0

    def is_high_confidence(self, threshold: float = 0.8) -> bool:
        return self.overall_confidence >= threshold


# Patterns for extracting claims from text
CLAIM_PATTERNS = [
    # "X is running/installed/available"
    r"(\w+(?:\s+\w+)*)\s+is\s+(running|installed|available|active|enabled|disabled|stopped)",
    # "There are N containers/services/packages"
    r"There\s+(?:are|is)\s+(\d+)\s+(\w+)",
    # "hostname is X"
    r"hostname\s+is\s+(\S+)",
    # "kernel version is X"
    r"kernel\s+(?:version\s+)?is\s+(\S+)",
    # "X GB of memory/disk"
    r"(\d+(?:\.\d+)?)\s*GB\s+(?:of\s+)?(\w+)",
]


class CertaintyWrapper:
    """Wraps LLM responses to ensure certainty and evidence grounding.

    This class:
    1. Extracts factual claims from LLM responses
    2. Validates claims against system state and tool outputs
    3. Flags unverified claims as uncertain
    4. Provides overall confidence scoring
    """

    def __init__(
        self,
        require_evidence: bool = True,
        max_inference_depth: int = 1,
        stale_threshold_seconds: int = 300,  # 5 minutes
    ):
        """Initialize the certainty wrapper.

        Args:
            require_evidence: If True, unverified claims reduce confidence
            max_inference_depth: How many inference steps are allowed
            stale_threshold_seconds: When to consider data stale
        """
        self.require_evidence = require_evidence
        self.max_inference_depth = max_inference_depth
        self.stale_threshold_seconds = stale_threshold_seconds

    def wrap_response(
        self,
        response: str,
        system_state: Any | None = None,
        tool_outputs: list[dict[str, Any]] | None = None,
        user_input: str = "",
    ) -> CertainResponse:
        """Wrap an LLM response with certainty tracking.

        Args:
            response: The raw LLM response
            system_state: SteadyState object with system information
            tool_outputs: List of tool call results
            user_input: The original user query

        Returns:
            CertainResponse with facts, uncertainties, and confidence
        """
        tool_outputs = tool_outputs or []

        # Extract claims from the response
        claims = self._extract_claims(response)

        facts = []
        uncertainties = []

        for claim in claims:
            # Try to find evidence for the claim
            evidence = self._find_evidence(claim, system_state, tool_outputs, user_input)

            if evidence and evidence.evidence_type != EvidenceType.NONE:
                facts.append(Fact(
                    claim=claim,
                    evidence=evidence,
                    verified=True,
                ))
            else:
                # No evidence - flag as uncertain
                uncertainties.append(Uncertainty(
                    claim=claim,
                    reason=UncertaintyReason.NO_DATA,
                    suggestion=self._suggest_verification(claim),
                    confidence=0.3,
                ))

        # Calculate overall confidence
        confidence = self._calculate_confidence(facts, uncertainties)

        # Generate evidence summary
        summary = self._generate_evidence_summary(facts, uncertainties)

        return CertainResponse(
            answer=response,
            facts=facts,
            uncertainties=uncertainties,
            overall_confidence=confidence,
            evidence_summary=summary,
        )

    def _extract_claims(self, response: str) -> list[str]:
        """Extract factual claims from response text."""
        claims = []

        # Use patterns to find structured claims
        for pattern in CLAIM_PATTERNS:
            matches = re.finditer(pattern, response, re.IGNORECASE)
            for match in matches:
                claims.append(match.group(0))

        # Also look for declarative sentences
        sentences = response.split(".")
        for sentence in sentences:
            sentence = sentence.strip()
            # Skip questions and conditionals
            if sentence.endswith("?") or sentence.lower().startswith(("if ", "when ", "maybe ")):
                continue
            # Look for declarative patterns
            if re.search(r"\b(is|are|has|have|running|installed)\b", sentence, re.IGNORECASE):
                if len(sentence) > 10:  # Skip very short fragments
                    claims.append(sentence)

        return list(set(claims))  # Deduplicate

    def _find_evidence(
        self,
        claim: str,
        system_state: Any | None,
        tool_outputs: list[dict[str, Any]],
        user_input: str,
    ) -> Evidence | None:
        """Find evidence supporting a claim."""
        claim_lower = claim.lower()

        # Check system state first (most reliable)
        if system_state:
            evidence = self._check_system_state(claim_lower, system_state)
            if evidence:
                return evidence

        # Check tool outputs
        for output in tool_outputs:
            evidence = self._check_tool_output(claim_lower, output)
            if evidence:
                return evidence

        # Check user input (user-stated facts)
        if user_input:
            evidence = self._check_user_input(claim_lower, user_input)
            if evidence:
                return evidence

        return None

    def _check_system_state(self, claim: str, system_state: Any) -> Evidence | None:
        """Check if system state supports the claim."""
        # Check hostname claims
        if "hostname" in claim:
            hostname = getattr(system_state, "hostname", None)
            if hostname and hostname.lower() in claim:
                return Evidence(
                    evidence_type=EvidenceType.SYSTEM_STATE,
                    source="SteadyState.hostname",
                    value=hostname,
                    timestamp=getattr(system_state, "collected_at", None),
                )

        # Check OS claims
        if "ubuntu" in claim or "debian" in claim or "fedora" in claim:
            os_name = getattr(system_state, "os_name", "").lower()
            if os_name and os_name in claim:
                return Evidence(
                    evidence_type=EvidenceType.SYSTEM_STATE,
                    source="SteadyState.os_name",
                    value=getattr(system_state, "os_pretty_name", os_name),
                    timestamp=getattr(system_state, "collected_at", None),
                )

        # Check kernel claims
        if "kernel" in claim:
            kernel = getattr(system_state, "kernel_version", None)
            if kernel and kernel in claim:
                return Evidence(
                    evidence_type=EvidenceType.SYSTEM_STATE,
                    source="SteadyState.kernel_version",
                    value=kernel,
                    timestamp=getattr(system_state, "collected_at", None),
                )

        # Check Docker claims
        if "docker" in claim:
            docker_installed = getattr(system_state, "docker_installed", False)
            docker_version = getattr(system_state, "docker_version", None)
            if "installed" in claim or "available" in claim:
                return Evidence(
                    evidence_type=EvidenceType.SYSTEM_STATE,
                    source="SteadyState.docker_installed",
                    value=f"installed={docker_installed}, version={docker_version}",
                    timestamp=getattr(system_state, "collected_at", None),
                )

        # Check service availability claims
        if "service" in claim:
            available_services = getattr(system_state, "available_services", [])
            for service in available_services:
                if service.lower() in claim:
                    return Evidence(
                        evidence_type=EvidenceType.SYSTEM_STATE,
                        source="SteadyState.available_services",
                        value=f"{service} is an available service",
                        timestamp=getattr(system_state, "collected_at", None),
                    )

        # Check memory claims
        if "memory" in claim or "ram" in claim or "gb" in claim:
            memory_gb = getattr(system_state, "memory_total_gb", 0)
            if memory_gb > 0:
                return Evidence(
                    evidence_type=EvidenceType.SYSTEM_STATE,
                    source="SteadyState.memory_total_gb",
                    value=f"{memory_gb:.1f} GB",
                    timestamp=getattr(system_state, "collected_at", None),
                )

        return None

    def _check_tool_output(self, claim: str, tool_output: dict[str, Any]) -> Evidence | None:
        """Check if tool output supports the claim."""
        tool_name = tool_output.get("tool", "")
        result = tool_output.get("result", {})
        timestamp = tool_output.get("timestamp")

        # Container claims
        if "container" in claim and "containers" in tool_name.lower():
            containers = result.get("all", result.get("running", []))
            for container in containers:
                name = container.get("name", "") if isinstance(container, dict) else str(container)
                if name.lower() in claim:
                    return Evidence(
                        evidence_type=EvidenceType.TOOL_OUTPUT,
                        source=tool_name,
                        value=container,
                        timestamp=datetime.fromisoformat(timestamp) if timestamp else None,
                    )

        # Service status claims
        if "running" in claim or "active" in claim or "stopped" in claim:
            if "service" in tool_name.lower():
                active = result.get("active", False)
                running = result.get("running", False)
                return Evidence(
                    evidence_type=EvidenceType.TOOL_OUTPUT,
                    source=tool_name,
                    value=f"active={active}, running={running}",
                    timestamp=datetime.fromisoformat(timestamp) if timestamp else None,
                )

        # Process claims
        if "process" in claim and "processes" in tool_name.lower():
            return Evidence(
                evidence_type=EvidenceType.TOOL_OUTPUT,
                source=tool_name,
                value=result,
                timestamp=datetime.fromisoformat(timestamp) if timestamp else None,
            )

        return None

    def _check_user_input(self, claim: str, user_input: str) -> Evidence | None:
        """Check if claim is based on user-provided information."""
        user_lower = user_input.lower()

        # If user mentioned something specific that's in the claim
        # This is for things like "you want to..." or "as you mentioned..."
        if "you" in claim or "your" in claim:
            return Evidence(
                evidence_type=EvidenceType.USER_INPUT,
                source="user_message",
                value=user_input[:100],
                confidence=0.9,
            )

        return None

    def _suggest_verification(self, claim: str) -> str | None:
        """Suggest how to verify an uncertain claim."""
        claim_lower = claim.lower()

        if any(kw in claim_lower for kw in ("calendar", "schedule", "event", "meeting")):
            return "Use cairn_get_calendar tool to verify calendar data"
        elif any(kw in claim_lower for kw in ("task", "todo", "reminder")):
            return "Use cairn_get_todos tool to verify task data"
        elif any(kw in claim_lower for kw in ("act", "scene", "play")):
            return "Use cairn_list_acts tool to verify Play data"

        return None

    def _calculate_confidence(
        self,
        facts: list[Fact],
        uncertainties: list[Uncertainty],
    ) -> float:
        """Calculate overall confidence score."""
        if not facts and not uncertainties:
            return 0.5  # Neutral if no claims

        total_claims = len(facts) + len(uncertainties)
        if total_claims == 0:
            return 0.5

        # Verified facts contribute positively
        verified_weight = sum(
            f.evidence.confidence for f in facts if f.verified
        )

        # Uncertainties reduce confidence
        uncertainty_weight = sum(u.confidence for u in uncertainties)

        # Calculate weighted confidence
        confidence = (verified_weight + uncertainty_weight) / total_claims

        # Apply penalty for having uncertainties
        if uncertainties:
            penalty = len(uncertainties) / total_claims * 0.2
            confidence = max(0.1, confidence - penalty)

        return min(1.0, max(0.0, confidence))

    def _generate_evidence_summary(
        self,
        facts: list[Fact],
        uncertainties: list[Uncertainty],
    ) -> str:
        """Generate human-readable evidence summary."""
        parts = []

        if facts:
            sources = list(set(f.evidence.source for f in facts))
            parts.append(f"Verified from: {', '.join(sources)}")

        if uncertainties:
            reasons = [u.reason.value for u in uncertainties]
            parts.append(f"Uncertain ({len(uncertainties)}): {', '.join(set(reasons))}")

        return "; ".join(parts) if parts else "No specific claims to verify"


def create_certainty_prompt_addition(system_state_context: str) -> str:
    """Create prompt addition that enforces certainty rules.

    This is added to LLM prompts to encourage evidence-based responses.
    """
    return f"""
{system_state_context}

CERTAINTY RULES (CRITICAL - MUST FOLLOW):

1. ONLY state facts you can verify from:
   - SYSTEM STATE above (for static facts about this machine)
   - Tool outputs (for current/dynamic state)
   - The user's message (for user-provided information)

2. When you DON'T have evidence, you MUST say so:
   - "I don't have information about X"
   - "I would need to check X to answer that"
   - "Based on [evidence], I believe X, but would need to verify"

3. NEVER guess or speculate about:
   - File contents you haven't read
   - Service states you haven't checked
   - Container configurations you haven't inspected
   - Network states you haven't verified

4. When making claims, cite your source:
   - "According to system state, ..."
   - "The [tool_name] shows ..."
   - "You mentioned ..."

5. If you need more information, ask to run a tool first.

Remember: It is ALWAYS better to say "I don't know" or "I need to check"
than to make an incorrect statement.
"""
