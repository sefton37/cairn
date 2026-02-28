"""4-Stage Compression Pipeline for conversation memories.

Transforms a conversation transcript into structured memories through local inference:
  Stage 1: Entity Extraction    → People, tasks, decisions, waiting-ons
  Stage 2: Narrative Compression → Meaning synthesis (2-4 sentences)
  Stage 3: State Delta           → Changes to knowledge graph
  Stage 4: Embedding Generation  → Semantic search via sentence transformers

All LLM stages use Ollama (local, free inference). Stage 4 uses sentence-transformers.

See docs/CONVERSATION_LIFECYCLE_SPEC.md for prompt templates and rationale.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from ..providers.ollama import OllamaProvider

logger = logging.getLogger(__name__)


# =============================================================================
# Prompt Templates
# =============================================================================

ENTITY_EXTRACTION_SYSTEM = """\
You are an entity extractor for a personal knowledge system. Given a conversation \
transcript, extract structured entities. Be precise. Only extract what is explicitly \
stated or strongly implied. Do not invent or assume.

Output valid JSON only. No preamble. No explanation."""

ENTITY_EXTRACTION_USER = """\
Extract entities from this conversation:

---
{transcript}
---

Extract into this structure:
{{
  "people": [{{"name": "", "context": "", "relation": ""}}],
  "tasks": [{{"description": "", "status": "decided|in_progress|blocked|completed",
              "priority": ""}}],
  "decisions": [{{"what": "", "why": ""}}],
  "waiting_on": [{{"who": "", "what": "", "since": ""}}],
  "questions_resolved": [{{"question": "", "answer": ""}}],
  "questions_opened": [{{"question": ""}}],
  "blockers_cleared": [{{"what": "", "unblocks": ""}}],
  "insights": [{{"insight": "", "context": ""}}]
}}

Only include categories that have entities. Empty categories should be omitted."""

NARRATIVE_SYSTEM = """\
You are a memory synthesizer. Given extracted entities from a conversation, write \
a brief narrative that captures the MEANING of the conversation — not what was said, \
but what it signified. Write as if you're a thoughtful colleague remembering what \
mattered about a discussion.

Keep it to 2-4 sentences. Focus on decisions, shifts in understanding, and what \
changed. Do not summarize the transcript. Synthesize the significance."""

NARRATIVE_USER = """\
Conversation entities:
{entities_json}

Conversation context:
- Date: {conversation_date}
- Message count: {message_count}

Write the memory narrative."""

STATE_DELTA_SYSTEM = """\
You are a state change detector. Given the entities extracted from a conversation \
and the current state of open threads, waiting-ons, and priorities, determine what \
changed.

Output valid JSON only."""

STATE_DELTA_USER = """\
Current open state:
{current_state_json}

Newly extracted entities:
{entities_json}

Determine state changes:
{{
  "new_waiting_ons": [{{"who": "", "what": ""}}],
  "resolved_waiting_ons": [{{"who": "", "what": ""}}],
  "new_open_threads": [{{"thread": "", "act": ""}}],
  "resolved_threads": [{{"thread": ""}}],
  "priority_changes": [{{"item": "", "old": "", "new": ""}}]
}}

Only include categories with actual changes. Be conservative — only mark something \
resolved if the conversation explicitly resolves it."""


# =============================================================================
# Data Types
# =============================================================================


@dataclass
class ExtractionResult:
    """Result of the full compression pipeline."""

    entities: dict[str, Any] = field(default_factory=dict)
    narrative: str = ""
    state_deltas: dict[str, Any] = field(default_factory=dict)
    embedding: bytes | None = None

    # Metadata
    model_used: str = ""
    duration_ms: int = 0
    passes: int = 0
    confidence: float = 0.0

    def entity_list(self) -> list[dict[str, Any]]:
        """Flatten entities into a list suitable for memory_entities table."""
        flat: list[dict[str, Any]] = []
        type_mapping = {
            "people": "person",
            "tasks": "task",
            "decisions": "decision",
            "waiting_on": "waiting_on",
            "questions_resolved": "question_resolved",
            "questions_opened": "question_opened",
            "blockers_cleared": "blocker_cleared",
            "insights": "insight",
        }
        for category, entity_type in type_mapping.items():
            for entity in self.entities.get(category, []):
                flat.append({"entity_type": entity_type, "entity_data": entity})
        return flat

    def delta_list(self) -> list[dict[str, Any]]:
        """Flatten state deltas into a list suitable for memory_state_deltas table."""
        flat: list[dict[str, Any]] = []
        type_mapping = {
            "new_waiting_ons": "new_waiting_on",
            "resolved_waiting_ons": "resolved_waiting_on",
            "new_open_threads": "new_thread",
            "resolved_threads": "resolved_thread",
            "priority_changes": "priority_change",
        }
        for category, delta_type in type_mapping.items():
            for delta in self.state_deltas.get(category, []):
                flat.append({"delta_type": delta_type, "delta_data": delta})
        return flat


# =============================================================================
# Pipeline
# =============================================================================


class CompressionPipeline:
    """4-stage compression pipeline using local inference.

    Each stage is independently callable for testing, but `compress()` runs
    the full pipeline in sequence.

    Args:
        provider: OllamaProvider instance for LLM inference.
        embedding_service: Optional EmbeddingService for stage 4.
            If None, stage 4 is skipped (embedding can be done later).
    """

    def __init__(
        self,
        provider: OllamaProvider | None = None,
        embedding_service: Any | None = None,
    ) -> None:
        self._provider = provider
        self._embedding_service = embedding_service

    def _get_provider(self) -> OllamaProvider:
        if self._provider is None:
            self._provider = OllamaProvider()
        return self._provider

    def compress(
        self,
        transcript: str,
        *,
        conversation_date: str = "",
        message_count: int = 0,
        current_open_state: dict[str, Any] | None = None,
    ) -> ExtractionResult:
        """Run the full 4-stage compression pipeline.

        Args:
            transcript: The conversation transcript (formatted messages).
            conversation_date: ISO date of the conversation.
            message_count: Number of messages in the conversation.
            current_open_state: Current open threads/waiting-ons for delta detection.

        Returns:
            ExtractionResult with entities, narrative, deltas, and embedding.
        """
        start = time.monotonic()
        passes = 0
        provider = self._get_provider()

        # Stage 1: Entity Extraction
        entities = self.extract_entities(transcript)
        passes += 1

        # Stage 2: Narrative Compression
        narrative = self.compress_narrative(
            entities,
            conversation_date=conversation_date,
            message_count=message_count,
        )
        passes += 1

        # Stage 3: State Delta Detection
        state_deltas = self.detect_state_deltas(
            entities,
            current_open_state=current_open_state or {},
        )
        passes += 1

        # Stage 4: Embedding Generation
        embedding = self.generate_embedding(narrative)
        if embedding:
            passes += 1

        duration_ms = int((time.monotonic() - start) * 1000)

        return ExtractionResult(
            entities=entities,
            narrative=narrative,
            state_deltas=state_deltas,
            embedding=embedding,
            model_used=getattr(provider, "_model", "unknown") or "unknown",
            duration_ms=duration_ms,
            passes=passes,
            confidence=self._estimate_confidence(entities, narrative),
        )

    def extract_entities(self, transcript: str) -> dict[str, Any]:
        """Stage 1: Extract structured entities from conversation transcript."""
        provider = self._get_provider()
        user_prompt = ENTITY_EXTRACTION_USER.format(transcript=transcript)

        try:
            raw = provider.chat_json(
                system=ENTITY_EXTRACTION_SYSTEM,
                user=user_prompt,
                temperature=0.1,
            )
            parsed = json.loads(raw)
            if not isinstance(parsed, dict):
                logger.warning("Entity extraction returned non-dict: %s", type(parsed))
                return {}
            return parsed
        except (json.JSONDecodeError, Exception) as e:
            logger.error("Entity extraction failed: %s", e)
            return {}

    def compress_narrative(
        self,
        entities: dict[str, Any],
        *,
        conversation_date: str = "",
        message_count: int = 0,
    ) -> str:
        """Stage 2: Generate narrative memory from extracted entities."""
        provider = self._get_provider()
        user_prompt = NARRATIVE_USER.format(
            entities_json=json.dumps(entities, indent=2),
            conversation_date=conversation_date or "unknown",
            message_count=message_count,
        )

        try:
            narrative = provider.chat_text(
                system=NARRATIVE_SYSTEM,
                user=user_prompt,
                temperature=0.3,
            )
            return narrative.strip()
        except Exception as e:
            logger.error("Narrative compression failed: %s", e)
            return ""

    def detect_state_deltas(
        self,
        entities: dict[str, Any],
        *,
        current_open_state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Stage 3: Detect state changes from entities vs current state."""
        provider = self._get_provider()
        user_prompt = STATE_DELTA_USER.format(
            current_state_json=json.dumps(current_open_state or {}, indent=2),
            entities_json=json.dumps(entities, indent=2),
        )

        try:
            raw = provider.chat_json(
                system=STATE_DELTA_SYSTEM,
                user=user_prompt,
                temperature=0.1,
            )
            parsed = json.loads(raw)
            if not isinstance(parsed, dict):
                logger.warning("State delta detection returned non-dict: %s", type(parsed))
                return {}
            return parsed
        except (json.JSONDecodeError, Exception) as e:
            logger.error("State delta detection failed: %s", e)
            return {}

    def generate_embedding(self, narrative: str) -> bytes | None:
        """Stage 4: Generate embedding for the narrative text."""
        if not narrative:
            return None

        if self._embedding_service is None:
            try:
                from ..memory.embeddings import EmbeddingService
                self._embedding_service = EmbeddingService()
            except ImportError:
                logger.warning("sentence-transformers not available, skipping embedding")
                return None

        return self._embedding_service.embed(narrative)

    def _estimate_confidence(
        self, entities: dict[str, Any], narrative: str
    ) -> float:
        """Estimate extraction quality based on heuristics."""
        if not entities and not narrative:
            return 0.0

        score = 0.5  # Base confidence

        # More entity types extracted = higher confidence
        entity_count = sum(len(v) for v in entities.values() if isinstance(v, list))
        if entity_count >= 3:
            score += 0.2
        elif entity_count >= 1:
            score += 0.1

        # Narrative exists and has substance
        if len(narrative) > 50:
            score += 0.2
        elif len(narrative) > 20:
            score += 0.1

        return min(score, 1.0)


def format_transcript(messages: list[dict[str, Any]]) -> str:
    """Format messages into a transcript string for the pipeline.

    Args:
        messages: List of message dicts with 'role' and 'content' keys.

    Returns:
        Formatted transcript string.
    """
    lines = []
    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        lines.append(f"[{role}]: {content}")
    return "\n\n".join(lines)
