"""Claude Code session observer — Phase 4 memory integration.

Processes completed Claude Code sessions in a background thread:
1. Summarize session transcript into a Cairn memory (pending_review)
2. Append summary to linked Scene notes (if agent has linked_scene_id)
3. Extract structured PM insights (tracking, lessons, patterns, decisions)

All outputs land in pending_review. Cairn never modifies The Play or
the memory graph without user action.

Runs in a background daemon thread + Queue — zero latency impact on
the session completion path.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from queue import Empty, Queue
from typing import Any
from uuid import uuid4

from ..play_db import _get_connection, _transaction
from ..providers.ollama import OllamaProvider
from ..rpc_handlers import RpcError
from .compression_pipeline import CompressionPipeline
from .memory_service import MemoryService

logger = logging.getLogger(__name__)


INSIGHT_EXTRACTION_SYSTEM = """You are a project observer for a software development team. Given a summary of a Claude Code agent session, extract structured observations. Be conservative — only extract what is clearly demonstrated.

Output valid JSON only. No preamble, no markdown fences."""

INSIGHT_EXTRACTION_USER = """Agent: {agent_name}
Purpose: {agent_purpose}
Session date: {date}
Files touched: {files}

Session narrative:
{narrative}

Extract:
{{
  "insights": [
    {{"type": "tracking|lesson|pattern|decision", "text": "one sentence"}}
  ]
}}

Rules:
- "tracking": factual status (completed X, worked on Y, blocked by Z)
- "lesson": something that took multiple attempts or failed before succeeding
- "pattern": a general approach discovered or confirmed
- "decision": a specific technical decision made (architecture, library, approach)
- Max 3 insights. If nothing notable, return empty array.
- Each insight text must be a single concise sentence."""


@dataclass
class CCSessionJob:
    """A completed CC session awaiting background analysis."""

    agent_id: str
    agent_name: str
    agent_purpose: str
    transcript: str
    stats: dict[str, Any]
    completed_at: str  # ISO timestamp


class CCSessionObserver:
    """Processes a completed CC session: summarize, store memory, extract insights.

    All outputs go to pending_review. Never modifies The Play autonomously.
    """

    def __init__(
        self,
        pipeline: CompressionPipeline | None = None,
        memory_service: MemoryService | None = None,
        provider: OllamaProvider | None = None,
    ) -> None:
        self._pipeline = pipeline
        self._memory_service = memory_service
        self._provider = provider

    def _get_pipeline(self) -> CompressionPipeline:
        if self._pipeline is None:
            self._pipeline = CompressionPipeline()
        return self._pipeline

    def _get_memory_service(self) -> MemoryService:
        if self._memory_service is None:
            self._memory_service = MemoryService()
        return self._memory_service

    def _get_provider(self) -> OllamaProvider:
        if self._provider is None:
            self._provider = OllamaProvider()
        return self._provider

    def process(self, job: CCSessionJob) -> None:
        """Synchronously process one completed session.

        Called by the queue worker thread. Order matters:
        1. Summarize → memory (4.1)
        2. Link to scene (4.2) — needs the narrative from step 1
        3. Extract insights (4.4) — needs the narrative from step 1
        """
        logger.info("Processing CC session for agent %s (%s)", job.agent_id, job.agent_name)

        narrative, memory_id = self._summarize_and_store(job)
        if narrative:
            self._maybe_link_scene(job, narrative)
            self._extract_and_store_insights(job, narrative, memory_id)

        logger.info("CC session processing complete for agent %s", job.agent_id)

    def _summarize_and_store(self, job: CCSessionJob) -> tuple[str, str | None]:
        """4.1: Summarize session transcript and store as a pending_review memory.

        Returns (narrative_text, memory_id) or ("", None) on failure.
        """
        try:
            pipeline = self._get_pipeline()
            entities = pipeline.extract_entities(job.transcript)
            if not entities:
                logger.info("No entities extracted for agent %s, skipping memory", job.agent_id)
                return "", None

            narrative = pipeline.compress_narrative(
                entities,
                conversation_date=job.completed_at[:10],
                message_count=job.stats.get("user_messages", 0),
            )
            if not narrative or len(narrative.strip()) < 20:
                logger.info("Narrative too short for agent %s, skipping memory", job.agent_id)
                return "", None

            synthetic_conv_id = f"cc-{job.agent_id}"
            memory_svc = self._get_memory_service()
            memory = memory_svc.store(
                conversation_id=synthetic_conv_id,
                narrative=narrative,
                model=getattr(self._get_provider(), "_model", ""),
                confidence=0.7,
                source="claudecode",
            )

            # Back-fill cc_agent_id
            if memory and memory.id:
                with _transaction() as conn:
                    conn.execute(
                        "UPDATE memories SET cc_agent_id = ? WHERE id = ?",
                        (job.agent_id, memory.id),
                    )
                logger.info("Created cc memory %s for agent %s", memory.id, job.agent_id)
                return narrative, memory.id

            return narrative, None
        except Exception:
            logger.exception("Failed to summarize session for agent %s", job.agent_id)
            return "", None

    def _maybe_link_scene(self, job: CCSessionJob, narrative: str) -> None:
        """4.2: Append session summary to linked Scene notes if configured."""
        try:
            conn = _get_connection()
            row = conn.execute(
                "SELECT linked_scene_id FROM cc_agents WHERE id = ?",
                (job.agent_id,),
            ).fetchone()
            if not row or not row["linked_scene_id"]:
                return

            scene_id = row["linked_scene_id"]
            scene_row = conn.execute(
                "SELECT act_id, notes FROM scenes WHERE scene_id = ?",
                (scene_id,),
            ).fetchone()
            if not scene_row:
                logger.warning("Linked scene %s not found for agent %s", scene_id, job.agent_id)
                return

            timestamp = job.completed_at[:10]
            capped_narrative = narrative[:500]
            existing_notes = (scene_row["notes"] or "").rstrip()
            appended = (
                existing_notes
                + f"\n\n---\n**CC Session {timestamp}:** {capped_narrative}\n"
            )

            with _transaction() as conn:
                conn.execute(
                    "UPDATE scenes SET notes = ? WHERE scene_id = ?",
                    (appended, scene_id),
                )
            logger.info("Appended session summary to scene %s", scene_id)
        except Exception:
            logger.exception("Failed to link scene for agent %s", job.agent_id)

    def _extract_and_store_insights(
        self, job: CCSessionJob, narrative: str, memory_id: str | None
    ) -> None:
        """4.4: Extract structured PM insights from the session narrative."""
        try:
            provider = self._get_provider()
            files_str = ", ".join(job.stats.get("files_touched", [])[:10]) or "none"

            user_prompt = INSIGHT_EXTRACTION_USER.format(
                agent_name=job.agent_name,
                agent_purpose=job.agent_purpose,
                date=job.completed_at[:10],
                files=files_str,
                narrative=narrative[:800],
            )

            raw = provider.chat_json(
                system=INSIGHT_EXTRACTION_SYSTEM,
                user=user_prompt,
                temperature=0.1,
            )
            parsed = json.loads(raw)
            insights = parsed.get("insights", [])
            if not isinstance(insights, list):
                return

            now = datetime.now(timezone.utc).isoformat()
            valid_types = {"tracking", "lesson", "pattern", "decision"}

            with _transaction() as conn:
                for insight in insights[:3]:
                    itype = insight.get("type", "")
                    itext = insight.get("text", "")
                    if itype not in valid_types or not itext:
                        continue

                    # Link decisions and patterns to the memory
                    linked_memory = memory_id if itype in ("decision", "pattern") else None

                    conn.execute(
                        """INSERT INTO cc_insights
                        (id, agent_id, session_completed_at, user_messages,
                         files_touched, insight_type, insight_text, memory_id,
                         status, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending_review', ?)""",
                        (
                            uuid4().hex,
                            job.agent_id,
                            job.completed_at,
                            job.stats.get("user_messages", 0),
                            files_str,
                            itype,
                            itext,
                            linked_memory,
                            now,
                        ),
                    )

            count = min(len(insights), 3)
            if count:
                logger.info("Stored %d insights for agent %s", count, job.agent_id)
        except Exception:
            logger.exception("Failed to extract insights for agent %s", job.agent_id)


class CCSessionObserverQueue:
    """Background daemon thread that processes CC session observations.

    Same pattern as TurnAssessmentQueue in turn_delta_assessor.py.
    """

    def __init__(self, observer: CCSessionObserver | None = None) -> None:
        self._observer = observer or CCSessionObserver()
        self._queue: Queue[CCSessionJob] = Queue()
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the background worker thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._worker,
            name="cc-session-observer",
            daemon=True,
        )
        self._thread.start()
        logger.info("CCSessionObserverQueue started")

    def stop(self) -> None:
        """Stop the background thread (waits up to 5 seconds)."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None
        logger.info("CCSessionObserverQueue stopped")

    def submit(self, job: CCSessionJob) -> None:
        """Enqueue a completed session for background analysis.

        Returns immediately — processing is asynchronous.
        """
        if not self._running:
            self.start()
        self._queue.put(job)
        logger.debug("Enqueued CC session job for agent %s", job.agent_id)

    def _worker(self) -> None:
        """Background worker: process jobs from the queue."""
        while self._running:
            try:
                job = self._queue.get(timeout=1.0)
            except Empty:
                continue

            try:
                self._observer.process(job)
            except Exception:
                logger.exception("CC session observer failed for agent %s", job.agent_id)
            finally:
                self._queue.task_done()


# --- Singleton ---

_instance: CCSessionObserverQueue | None = None
_lock = threading.Lock()


def get_cc_session_observer() -> CCSessionObserverQueue:
    """Get or create the singleton CCSessionObserverQueue."""
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = CCSessionObserverQueue()
                _instance.start()
    return _instance
