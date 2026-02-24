"""Background Compression Manager.

Runs the CompressionPipeline in a background thread, managing the
conversation state transitions and storing results.

Design:
- Single daemon thread processes one conversation at a time
- Queue-based job submission (thread-safe)
- Status polling for UI updates
- Error recovery: failed compression resets status to ready_to_close
- No shared mutable state between threads (thread-local DB connections)

See docs/CONVERSATION_LIFECYCLE_SPEC.md for lifecycle details.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from queue import Empty, Queue
from typing import Any
from uuid import uuid4

from ..play_db import (
    _transaction,
    init_db,
)
from .compression_pipeline import CompressionPipeline, ExtractionResult, format_transcript
from .conversation_service import ConversationService
from .memory_service import MemoryService

logger = logging.getLogger(__name__)


@dataclass
class CompressionJob:
    """A queued compression job."""

    conversation_id: str


@dataclass
class CompressionStatus:
    """Status of a compression job."""

    conversation_id: str
    state: str  # "queued", "running", "completed", "failed"
    error: str | None = None
    result_memory_ids: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "conversation_id": self.conversation_id,
            "state": self.state,
            "error": self.error,
            "result_memory_ids": self.result_memory_ids,
        }


class CompressionManager:
    """Manages background compression of conversations.

    Thread-safe. Submit jobs via `submit()`, poll status via `get_status()`.

    Usage:
        manager = CompressionManager()
        manager.start()

        # Submit a conversation for compression
        manager.submit("conv-123")

        # Poll for status
        status = manager.get_status("conv-123")
    """

    def __init__(
        self,
        pipeline: CompressionPipeline | None = None,
        memory_service: MemoryService | None = None,
    ) -> None:
        self._pipeline = pipeline or CompressionPipeline()
        self._memory_service = memory_service
        self._queue: Queue[CompressionJob] = Queue()
        self._statuses: dict[str, CompressionStatus] = {}
        self._status_lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._running = False
        self._conversation_service = ConversationService()

    def _get_memory_service(self) -> MemoryService:
        if self._memory_service is None:
            self._memory_service = MemoryService()
        return self._memory_service

    def start(self) -> None:
        """Start the background compression thread."""
        if self._thread is not None and self._thread.is_alive():
            return

        self._running = True
        self._thread = threading.Thread(
            target=self._worker,
            name="compression-worker",
            daemon=True,
        )
        self._thread.start()
        logger.info("Compression manager started")

    def stop(self) -> None:
        """Stop the background compression thread."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None
        logger.info("Compression manager stopped")

    def submit(self, conversation_id: str) -> CompressionStatus:
        """Submit a conversation for compression.

        The conversation should already be in 'ready_to_close' status.

        Returns:
            Initial CompressionStatus (queued).
        """
        status = CompressionStatus(
            conversation_id=conversation_id,
            state="queued",
        )
        with self._status_lock:
            self._statuses[conversation_id] = status

        self._queue.put(CompressionJob(conversation_id=conversation_id))
        logger.info("Queued compression for conversation %s", conversation_id)
        return status

    def get_status(self, conversation_id: str) -> CompressionStatus | None:
        """Get the current status of a compression job."""
        with self._status_lock:
            return self._statuses.get(conversation_id)

    def _update_status(
        self,
        conversation_id: str,
        state: str,
        *,
        error: str | None = None,
        memory_ids: list[str] | None = None,
    ) -> None:
        with self._status_lock:
            self._statuses[conversation_id] = CompressionStatus(
                conversation_id=conversation_id,
                state=state,
                error=error,
                result_memory_ids=memory_ids,
            )

    def _worker(self) -> None:
        """Background worker that processes compression jobs."""
        logger.info("Compression worker thread started")
        while self._running:
            try:
                job = self._queue.get(timeout=1.0)
            except Empty:
                continue

            self._process_job(job)

        logger.info("Compression worker thread stopped")

    def _process_job(self, job: CompressionJob) -> None:
        """Process a single compression job."""
        conv_id = job.conversation_id
        logger.info("Processing compression for conversation %s", conv_id)

        try:
            # Transition to compressing
            self._conversation_service.start_compression(conv_id)
            self._update_status(conv_id, "running")

            # Get conversation messages
            messages = self._conversation_service.get_messages(conv_id)
            if not messages:
                logger.warning("No messages in conversation %s, skipping", conv_id)
                self._conversation_service.fail_compression(conv_id)
                self._update_status(conv_id, "failed", error="No messages to compress")
                return

            # Format transcript
            transcript = format_transcript(
                [{"role": m.role, "content": m.content} for m in messages]
            )

            # Get conversation metadata
            conv = self._conversation_service.get_by_id(conv_id)

            # Run compression pipeline
            result = self._pipeline.compress(
                transcript,
                conversation_date=conv.started_at if conv else "",
                message_count=len(messages),
            )

            # Store results
            memory_ids = self._store_results(conv_id, result)

            # Mark as completed (still needs user review before archive)
            self._update_status(conv_id, "completed", memory_ids=memory_ids)
            logger.info(
                "Compression complete for %s: %d entities, %d deltas, "
                "narrative=%d chars, %dms",
                conv_id,
                len(result.entity_list()),
                len(result.delta_list()),
                len(result.narrative),
                result.duration_ms,
            )

        except Exception as e:
            logger.error("Compression failed for %s: %s", conv_id, e, exc_info=True)
            try:
                self._conversation_service.fail_compression(conv_id)
            except Exception:
                logger.error("Failed to roll back compression state for %s", conv_id)
            self._update_status(conv_id, "failed", error=str(e))

    def _store_results(
        self, conversation_id: str, result: ExtractionResult
    ) -> list[str]:
        """Store compression results via MemoryService (with deduplication).

        Delegates memory creation to MemoryService.store() which handles:
        - Deduplication via embedding similarity + LLM judgment
        - Signal strengthening (reinforce existing vs create new)
        - Block creation, graph relationships, embeddings

        Entities and state deltas are stored as supplementary data on the
        resulting memory.

        Returns:
            List of memory IDs (created or reinforced).
        """
        init_db()
        memory_service = self._get_memory_service()

        # Store memory via MemoryService (handles dedup)
        memory = memory_service.store(
            conversation_id,
            result.narrative,
            embedding=result.embedding,
            model=result.model_used,
            confidence=result.confidence,
        )

        # Store entities and deltas as supplementary data
        now_iso = _now_iso()
        with _transaction() as conn:
            for entity in result.entity_list():
                entity_id = uuid4().hex[:12]
                conn.execute(
                    """INSERT INTO memory_entities (id, memory_id, entity_type,
                       entity_data, created_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (
                        entity_id,
                        memory.id,
                        entity["entity_type"],
                        json.dumps(entity["entity_data"]),
                        now_iso,
                    ),
                )

            for delta in result.delta_list():
                delta_id = uuid4().hex[:12]
                conn.execute(
                    """INSERT INTO memory_state_deltas (id, memory_id, delta_type,
                       delta_data)
                       VALUES (?, ?, ?, ?)""",
                    (
                        delta_id,
                        memory.id,
                        delta["delta_type"],
                        json.dumps(delta["delta_data"]),
                    ),
                )

            # Update conversation compression metadata
            conn.execute(
                """UPDATE conversations SET
                   compression_model = ?,
                   compression_duration_ms = ?,
                   compression_passes = ?
                   WHERE id = ?""",
                (
                    result.model_used,
                    result.duration_ms,
                    result.passes,
                    conversation_id,
                ),
            )

        logger.info(
            "Stored memory %s for conversation %s (%d entities, %d deltas)",
            memory.id,
            conversation_id,
            len(result.entity_list()),
            len(result.delta_list()),
        )
        return [memory.id]


def _now_iso() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()


# Singleton manager
_manager: CompressionManager | None = None
_manager_lock = threading.Lock()


def get_compression_manager() -> CompressionManager:
    """Get or create the singleton CompressionManager."""
    global _manager
    if _manager is None:
        with _manager_lock:
            if _manager is None:
                _manager = CompressionManager()
                _manager.start()
    return _manager
