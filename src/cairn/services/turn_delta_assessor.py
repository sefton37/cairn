"""Per-Turn Delta Assessor.

After each CAIRN response, a lightweight LLM classification decides if new
knowledge emerged. If so, creates a memory immediately via MemoryService.store().

Design decisions:
- Only NO_CHANGE vs CREATE — no UPDATE. MemoryService.store() dedup handles reinforcement.
- JSON parse failures default to NO_CHANGE (never raises).
- All mid-turn memories enter as pending_review.
- Runs in a background queue (daemon thread + Queue) — zero latency impact on chat.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from queue import Empty, Queue
from uuid import uuid4

from ..play_db import _transaction, init_db
from ..providers.ollama import OllamaProvider
from .compression_pipeline import CompressionPipeline
from .memory_service import MemoryService

logger = logging.getLogger(__name__)


# =============================================================================
# Prompt Templates
# =============================================================================

CLASSIFICATION_SYSTEM = """\
You are a knowledge detector. Given a conversation turn, decide if genuinely NEW \
knowledge was established — a decision made, a fact revealed, a preference stated, \
a commitment given.

Be CONSERVATIVE. Casual chat, questions without answers, re-statements of known \
facts are NOT new knowledge. Output valid JSON only."""

CLASSIFICATION_USER = """\
User said: {user_message}
CAIRN responded: {cairn_response}
Known context: {known_memories}

Did this turn establish NEW knowledge?
{{"assessment": "NO_CHANGE" | "CREATE", "what": "one sentence or empty"}}

Rules:
- NO_CHANGE for questions, casual chat, known information
- CREATE only for clear decisions, commitments, preferences, facts
- When in doubt, NO_CHANGE"""

TYPE_CLASSIFICATION_SYSTEM = """\
You are a memory type classifier. Given a compressed memory narrative, classify it into \
exactly one of these types:
- fact: A stable assertion about the world or the user. "I work at Acme."
- preference: A preference or style. "I prefer concise answers."
- relationship: A relationship between people. "Alex is my manager."
- commitment: A promise, obligation, or deadline. "I told Sarah I'd review by Thursday."
- priority: A relative ordering or urgency decision. "Shipping the demo matters more right now."

Output valid JSON only. No preamble."""

TYPE_CLASSIFICATION_USER = """\
Memory narrative:
{narrative}

Classify this memory:
{{"memory_type": "fact"|"preference"|"relationship"|"commitment"|"priority",
  "confidence": 0.0-1.0,
  "reason": "brief explanation"}}"""

VALID_MEMORY_TYPES: frozenset[str] = frozenset(
    {"fact", "preference", "priority", "commitment", "relationship"}
)


# =============================================================================
# Data Types
# =============================================================================


import re


def _strip_code_fences(text: str) -> str:
    """Strip markdown code fences from LLM JSON responses.

    Some models (e.g. Anthropic) wrap JSON in ```json ... ``` blocks.
    """
    stripped = re.sub(r"^```(?:json)?\s*\n?", "", text.strip())
    stripped = re.sub(r"\n?```\s*$", "", stripped)
    return stripped.strip()


def _now_iso() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()


def _new_id() -> str:
    return uuid4().hex[:12]


@dataclass
class TurnAssessment:
    """Result of assessing a single conversation turn."""

    conversation_id: str
    turn_position: int
    assessment: str  # 'NO_CHANGE' | 'CREATE'
    what: str  # one-line description, empty for NO_CHANGE
    memory_id: str | None  # populated if memory created
    model_used: str
    duration_ms: int


@dataclass
class _AssessmentJob:
    """A queued turn assessment job."""

    conversation_id: str
    turn_position: int
    user_message: str
    cairn_response: str
    relevant_memories: list[str] = field(default_factory=list)


# =============================================================================
# Assessor
# =============================================================================


class TurnDeltaAssessor:
    """Assesses individual conversation turns for new knowledge.

    Runs a lightweight LLM classification per turn. On CREATE, runs compression
    stages 1-3 to extract a narrative and stores it via MemoryService.

    Usage:
        assessor = TurnDeltaAssessor()
        result = assessor.assess_turn(
            conversation_id="conv-abc",
            turn_position=3,
            user_message="I've decided to use PostgreSQL",
            cairn_response="That makes sense for your use case.",
        )
    """

    def __init__(
        self,
        provider: OllamaProvider | None = None,
        memory_service: MemoryService | None = None,
        compression_pipeline: CompressionPipeline | None = None,
    ) -> None:
        self._provider = provider
        self._memory_service = memory_service
        self._compression_pipeline = compression_pipeline
        init_db()

    def _get_provider(self) -> OllamaProvider:
        if self._provider is None:
            self._provider = OllamaProvider()
        return self._provider

    def _get_memory_service(self) -> MemoryService:
        if self._memory_service is None:
            self._memory_service = MemoryService()
        return self._memory_service

    def _get_pipeline(self) -> CompressionPipeline:
        if self._compression_pipeline is None:
            self._compression_pipeline = CompressionPipeline(provider=self._provider)
        return self._compression_pipeline

    @staticmethod
    def _get_observer():
        """Get the consciousness observer (lazy import to avoid circular deps)."""
        from cairn.cairn.consciousness_stream import ConsciousnessObserver

        return ConsciousnessObserver.get_instance()

    def assess_turn(
        self,
        conversation_id: str,
        turn_position: int,
        user_message: str,
        cairn_response: str,
        relevant_memories: list[str] | None = None,
    ) -> TurnAssessment:
        """Synchronously assess a conversation turn for new knowledge.

        Writes an audit row to turn_assessments regardless of outcome.
        On CREATE, extracts a narrative and stores a memory.

        Args:
            conversation_id: The lifecycle conversation ID.
            turn_position: Index of this turn within the conversation.
            user_message: The user's message text.
            cairn_response: CAIRN's response text.
            relevant_memories: Optional list of known memory narratives for context.

        Returns:
            TurnAssessment with the classification result and any created memory_id.
        """
        from cairn.cairn.consciousness_stream import ConsciousnessEventType

        observer = self._get_observer()
        start = time.monotonic()
        memories = relevant_memories or []

        observer.emit(
            ConsciousnessEventType.MEMORY_ASSESSING,
            "Evaluating turn for new knowledge",
            f"Turn {turn_position} in conversation {conversation_id[:8]}...",
            turn_position=turn_position,
        )

        assessment, what = self._classify_turn(user_message, cairn_response, memories)

        memory_id: str | None = None
        if assessment == "CREATE":
            memory_id = self._extract_and_store(
                conversation_id, user_message, cairn_response
            )
            observer.emit(
                ConsciousnessEventType.MEMORY_CREATED,
                f"Memory created: {what}" if what else "Memory created",
                what or "New knowledge extracted from turn",
                memory_id=memory_id,
            )
        else:
            observer.emit(
                ConsciousnessEventType.MEMORY_NO_CHANGE,
                "No new knowledge",
                what or "Turn did not establish new knowledge",
            )

        duration_ms = int((time.monotonic() - start) * 1000)
        provider = self._get_provider()
        model_used = getattr(provider, "_model", "") or ""

        result = TurnAssessment(
            conversation_id=conversation_id,
            turn_position=turn_position,
            assessment=assessment,
            what=what,
            memory_id=memory_id,
            model_used=model_used,
            duration_ms=duration_ms,
        )

        self._persist_assessment(result)
        return result

    def _classify_turn(
        self,
        user_message: str,
        cairn_response: str,
        relevant_memories: list[str],
    ) -> tuple[str, str]:
        """Ask the LLM whether this turn established new knowledge.

        Returns:
            (assessment, what) — ('NO_CHANGE'|'CREATE', one-line description)
            On any parse failure, returns ('NO_CHANGE', '').
        """
        known = "\n".join(f"- {m}" for m in relevant_memories) if relevant_memories else "(none)"
        user_prompt = CLASSIFICATION_USER.format(
            user_message=user_message,
            cairn_response=cairn_response,
            known_memories=known,
        )

        try:
            provider = self._get_provider()
            raw = provider.chat_json(
                system=CLASSIFICATION_SYSTEM,
                user=user_prompt,
                temperature=0.1,
            )
            parsed = json.loads(_strip_code_fences(raw))
            if not isinstance(parsed, dict):
                logger.warning("Turn classification returned non-dict, defaulting NO_CHANGE")
                return "NO_CHANGE", ""

            assessment = parsed.get("assessment", "NO_CHANGE")
            if assessment not in ("NO_CHANGE", "CREATE"):
                logger.warning("Unexpected assessment value %r, defaulting NO_CHANGE", assessment)
                assessment = "NO_CHANGE"

            what = parsed.get("what", "") or ""
            return assessment, what

        except (json.JSONDecodeError, Exception) as e:
            logger.warning("Turn classification failed, defaulting NO_CHANGE: %s", e)
            return "NO_CHANGE", ""

    def _classify_memory_type(self, narrative: str) -> str | None:
        """Classify a memory narrative into a type category.

        Returns the type string ('fact', 'preference', 'relationship',
        'commitment', or 'priority'), or None on any failure.

        None is the safe default — callers should treat it as unclassified.
        """
        user_prompt = TYPE_CLASSIFICATION_USER.format(narrative=narrative)
        try:
            provider = self._get_provider()
            raw = provider.chat_json(
                system=TYPE_CLASSIFICATION_SYSTEM,
                user=user_prompt,
                temperature=0.1,
            )
            parsed = json.loads(_strip_code_fences(raw))
            if not isinstance(parsed, dict):
                logger.warning("Memory type classification returned non-dict, ignoring")
                return None

            memory_type = parsed.get("memory_type")
            if memory_type not in VALID_MEMORY_TYPES:
                logger.warning(
                    "Memory type classification returned invalid type %r, ignoring",
                    memory_type,
                )
                return None

            return memory_type

        except Exception as e:
            logger.warning("Memory type classification failed, skipping: %s", e)
            return None

    def _extract_and_store(
        self,
        conversation_id: str,
        user_message: str,
        cairn_response: str,
    ) -> str | None:
        """Run compression stages 1-3 on the turn pair and store as a memory.

        Runs entity extraction, narrative compression, and state delta detection
        against the two-message mini-transcript. Skips embedding (stage 4) —
        MemoryService.store() will generate it if sentence-transformers is available.

        Returns:
            The memory_id of the created (or reinforced) memory, or None on failure.
        """
        transcript = f"[user]: {user_message}\n\n[cairn]: {cairn_response}"
        pipeline = self._get_pipeline()

        try:
            entities = pipeline.extract_entities(transcript)
            narrative = pipeline.compress_narrative(entities)

            if not narrative:
                logger.warning(
                    "Turn narrative compression produced empty result for conv %s",
                    conversation_id,
                )
                return None

            memory_service = self._get_memory_service()
            memory = memory_service.store(
                conversation_id,
                narrative,
                source="turn_assessment",
            )
            logger.info(
                "Created turn-assessment memory %s for conv %s",
                memory.id,
                conversation_id,
            )

            # Classify the memory type in a second lightweight LLM call.
            # Failure is non-fatal — memory_type defaults to NULL.
            memory_type = self._classify_memory_type(narrative)
            if memory_type is not None:
                memory_service.set_memory_type(memory.id, memory_type)

            return memory.id

        except Exception as e:
            logger.error(
                "Failed to extract and store turn memory for conv %s: %s",
                conversation_id,
                e,
                exc_info=True,
            )
            return None

    def _persist_assessment(self, result: TurnAssessment) -> None:
        """Write the assessment row to turn_assessments for audit trail."""
        try:
            row_id = _new_id()
            now = _now_iso()
            with _transaction() as conn:
                conn.execute(
                    """INSERT INTO turn_assessments
                       (id, conversation_id, turn_position, assessment,
                        memory_id, model_used, duration_ms, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        row_id,
                        result.conversation_id,
                        result.turn_position,
                        result.assessment,
                        result.memory_id,
                        result.model_used,
                        result.duration_ms,
                        now,
                    ),
                )
            logger.debug(
                "Persisted turn assessment %s (%s) for conv %s turn %d",
                row_id,
                result.assessment,
                result.conversation_id,
                result.turn_position,
            )
        except Exception as e:
            # Never raise from persistence — the assessment already happened.
            logger.warning("Failed to persist turn assessment row: %s", e)


# =============================================================================
# Background Queue
# =============================================================================


class TurnAssessmentQueue:
    """Background daemon thread that processes turn assessments asynchronously.

    Submit jobs with submit(); the worker calls TurnDeltaAssessor.assess_turn()
    on each job without blocking the caller.

    Usage:
        queue = TurnAssessmentQueue()
        queue.start()

        queue.submit(
            conversation_id="conv-abc",
            turn_position=3,
            user_message="I've decided to use PostgreSQL",
            cairn_response="That makes sense for your use case.",
        )

        queue.stop()  # Clean shutdown (waits up to 5s)
    """

    def __init__(
        self,
        assessor: TurnDeltaAssessor | None = None,
    ) -> None:
        self._assessor = assessor
        self._queue: Queue[_AssessmentJob] = Queue()
        self._thread: threading.Thread | None = None
        self._running = False

    def _get_assessor(self) -> TurnDeltaAssessor:
        if self._assessor is None:
            self._assessor = TurnDeltaAssessor()
        return self._assessor

    def start(self) -> None:
        """Start the background assessment thread."""
        if self._thread is not None and self._thread.is_alive():
            return

        self._running = True
        self._thread = threading.Thread(
            target=self._worker,
            name="turn-assessment-worker",
            daemon=True,
        )
        self._thread.start()
        logger.info("TurnAssessmentQueue started")

    def stop(self) -> None:
        """Stop the background assessment thread (waits up to 5 seconds)."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None
        logger.info("TurnAssessmentQueue stopped")

    def submit(
        self,
        conversation_id: str,
        turn_position: int,
        user_message: str,
        cairn_response: str,
        relevant_memories: list[str] | None = None,
    ) -> None:
        """Enqueue a turn for background assessment.

        Returns immediately — processing is asynchronous.
        """
        job = _AssessmentJob(
            conversation_id=conversation_id,
            turn_position=turn_position,
            user_message=user_message,
            cairn_response=cairn_response,
            relevant_memories=relevant_memories or [],
        )
        self._queue.put(job)
        logger.debug(
            "Queued turn assessment for conv %s turn %d",
            conversation_id,
            turn_position,
        )

    def _worker(self) -> None:
        """Background worker loop — processes one job at a time."""
        logger.info("Turn assessment worker thread started")
        while self._running:
            try:
                job = self._queue.get(timeout=1.0)
            except Empty:
                continue

            self._process_job(job)

        logger.info("Turn assessment worker thread stopped")

    def _process_job(self, job: _AssessmentJob) -> None:
        """Process a single assessment job, swallowing all exceptions."""
        try:
            assessor = self._get_assessor()
            result = assessor.assess_turn(
                conversation_id=job.conversation_id,
                turn_position=job.turn_position,
                user_message=job.user_message,
                cairn_response=job.cairn_response,
                relevant_memories=job.relevant_memories,
            )
            logger.info(
                "Turn assessment complete for conv %s turn %d: %s",
                job.conversation_id,
                job.turn_position,
                result.assessment,
            )
        except Exception as e:
            logger.error(
                "Turn assessment job failed for conv %s turn %d: %s",
                job.conversation_id,
                job.turn_position,
                e,
                exc_info=True,
            )


# =============================================================================
# Singleton
# =============================================================================

_queue_instance: TurnAssessmentQueue | None = None
_queue_lock = threading.Lock()


def get_turn_assessment_queue() -> TurnAssessmentQueue:
    """Get or create the singleton TurnAssessmentQueue (auto-started)."""
    global _queue_instance
    if _queue_instance is None:
        with _queue_lock:
            if _queue_instance is None:
                _queue_instance = TurnAssessmentQueue()
                _queue_instance.start()
    return _queue_instance
