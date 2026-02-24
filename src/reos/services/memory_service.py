"""Memory Storage, Routing & Review Service.

Manages the full memory lifecycle after compression:
- Store: Deduplicate via embedding similarity + LLM judgment, reinforce or create
- Route: Direct memories to destination Act (default: Your Story)
- Review: Gate memories through user review before they enter the reasoning pool
- Correct/Supersede: Memory correction with signal_count inheritance

Deduplication flow (signal strengthening):
1. EmbeddingService.find_similar() fetches candidate memories above threshold
2. If candidates exist, Ollama chat_json() judges substantive match
3. Match found → increment signal_count, update last_reinforced_at
4. No match → create new memory with signal_count=1

See docs/CONVERSATION_LIFECYCLE_SPEC.md for specification.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from ..memory.embeddings import EmbeddingService, get_embedding_service
from ..memory.graph_store import MemoryGraphStore
from ..memory.relationships import RelationshipSource, RelationshipType
from ..play_db import (
    YOUR_STORY_ACT_ID,
    _get_connection,
    _transaction,
    init_db,
)
from ..providers.ollama import OllamaProvider

logger = logging.getLogger(__name__)


# =============================================================================
# Prompt Templates
# =============================================================================

DEDUP_JUDGMENT_SYSTEM = """\
You are a memory deduplication judge. Given a NEW memory and an EXISTING memory, \
determine if they represent the SAME insight, decision, or fact — not just \
semantically similar topics, but substantively identical conclusions.

Two memories can be semantically close but substantively different:
- "Alex prefers email" vs "Alex prefers Slack" → DIFFERENT (opposite conclusions)
- "We decided to use SQLite" vs "The team chose SQLite for storage" → SAME

Output valid JSON only. No preamble."""

DEDUP_JUDGMENT_USER = """\
NEW memory:
{new_narrative}

EXISTING memory (signal_count={signal_count}):
{existing_narrative}

Are these the SAME substantive insight/decision/fact?
{{
  "is_match": true/false,
  "reason": "brief explanation",
  "merged_narrative": "if match, an improved narrative combining both; else empty string"
}}"""


# =============================================================================
# Data Types
# =============================================================================


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _new_id() -> str:
    return uuid4().hex[:12]


@dataclass
class Memory:
    """A compressed memory from a conversation."""

    id: str
    block_id: str
    conversation_id: str
    narrative: str
    destination_act_id: str | None
    is_your_story: bool
    status: str
    signal_count: int
    last_reinforced_at: str | None
    extraction_model: str | None
    extraction_confidence: float | None
    user_reviewed: bool
    user_edited: bool
    original_narrative: str | None
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "block_id": self.block_id,
            "conversation_id": self.conversation_id,
            "narrative": self.narrative,
            "destination_act_id": self.destination_act_id,
            "is_your_story": self.is_your_story,
            "status": self.status,
            "signal_count": self.signal_count,
            "last_reinforced_at": self.last_reinforced_at,
            "extraction_model": self.extraction_model,
            "extraction_confidence": self.extraction_confidence,
            "user_reviewed": self.user_reviewed,
            "user_edited": self.user_edited,
            "original_narrative": self.original_narrative,
            "created_at": self.created_at,
        }

    @classmethod
    def from_row(cls, row: Any) -> Memory:
        return cls(
            id=row["id"],
            block_id=row["block_id"],
            conversation_id=row["conversation_id"],
            narrative=row["narrative"],
            destination_act_id=row["destination_act_id"],
            is_your_story=bool(row["is_your_story"]),
            status=row["status"],
            signal_count=row["signal_count"],
            last_reinforced_at=row["last_reinforced_at"],
            extraction_model=row["extraction_model"],
            extraction_confidence=row["extraction_confidence"],
            user_reviewed=bool(row["user_reviewed"]),
            user_edited=bool(row["user_edited"]),
            original_narrative=row["original_narrative"],
            created_at=row["created_at"],
        )


@dataclass
class DeduplicationResult:
    """Result of the deduplication check."""

    is_duplicate: bool
    matched_memory_id: str | None = None
    reason: str = ""
    merged_narrative: str = ""


# =============================================================================
# Service
# =============================================================================


class MemoryService:
    """Manages memory storage, deduplication, routing, and review.

    Thread-safe via play_db's thread-local connections.

    Usage:
        service = MemoryService()

        # Store with dedup (called by CompressionManager)
        memory = service.store(
            conversation_id="conv-123",
            narrative="We decided to use SQLite.",
            embedding=b"...",
            model="qwen2.5:1.5b",
            confidence=0.8,
        )

        # Review gate
        pending = service.get_pending_review()
        service.approve(memory.id)
    """

    def __init__(
        self,
        provider: OllamaProvider | None = None,
        embedding_service: EmbeddingService | None = None,
        graph_store: MemoryGraphStore | None = None,
        similarity_threshold: float = 0.7,
    ) -> None:
        self._provider = provider
        self._embedding_service = embedding_service
        self._graph_store = graph_store
        self._similarity_threshold = similarity_threshold
        init_db()

    def _get_provider(self) -> OllamaProvider:
        if self._provider is None:
            self._provider = OllamaProvider()
        return self._provider

    def _get_embedding_service(self) -> EmbeddingService:
        if self._embedding_service is None:
            self._embedding_service = get_embedding_service()
        return self._embedding_service

    def _get_graph_store(self) -> MemoryGraphStore:
        if self._graph_store is None:
            self._graph_store = MemoryGraphStore()
        return self._graph_store

    # -------------------------------------------------------------------------
    # Store (with deduplication)
    # -------------------------------------------------------------------------

    def store(
        self,
        conversation_id: str,
        narrative: str,
        *,
        embedding: bytes | None = None,
        model: str = "",
        confidence: float = 0.0,
        destination_act_id: str | None = None,
    ) -> Memory:
        """Store a memory with deduplication via signal strengthening.

        Flow:
        1. Generate embedding if not provided
        2. Find similar existing memories via embedding distance
        3. If candidates found, use LLM judgment for substantive match
        4. Match → reinforce existing memory (signal_count++)
        5. No match → create new memory

        Args:
            conversation_id: Source conversation.
            narrative: The compressed narrative text.
            embedding: Pre-computed embedding bytes, or None to generate.
            model: Model used for extraction.
            confidence: Extraction confidence score.
            destination_act_id: Target Act, or None for Your Story.

        Returns:
            The created or reinforced Memory.
        """
        # Generate embedding if not provided
        if embedding is None:
            try:
                embedding = self._get_embedding_service().embed(narrative)
            except Exception:
                logger.warning("Failed to generate embedding for dedup, skipping")

        # Check for duplicates
        dedup = self._check_duplicate(narrative, embedding)

        if dedup.is_duplicate and dedup.matched_memory_id:
            return self._reinforce(
                dedup.matched_memory_id,
                conversation_id,
                merged_narrative=dedup.merged_narrative,
            )

        return self._create_memory(
            conversation_id=conversation_id,
            narrative=narrative,
            embedding=embedding,
            model=model,
            confidence=confidence,
            destination_act_id=destination_act_id,
        )

    def _check_duplicate(
        self, narrative: str, embedding: bytes | None
    ) -> DeduplicationResult:
        """Check if a narrative matches an existing memory.

        Uses embedding similarity as filter, then LLM judgment as arbiter.
        """
        if not embedding:
            return DeduplicationResult(is_duplicate=False, reason="No embedding available")

        # Get all existing memory embeddings
        candidates = self._get_candidate_memories(embedding)
        if not candidates:
            return DeduplicationResult(is_duplicate=False, reason="No similar memories found")

        # LLM judgment on top candidates
        for memory_id, _similarity, existing_narrative, signal_count in candidates:
            judgment = self._judge_duplicate(
                narrative, existing_narrative, signal_count
            )
            if judgment.is_duplicate:
                judgment.matched_memory_id = memory_id
                return judgment

        return DeduplicationResult(is_duplicate=False, reason="No substantive matches")

    def _get_candidate_memories(
        self, query_embedding: bytes, top_k: int = 5
    ) -> list[tuple[str, float, str, int]]:
        """Find existing memories with similar embeddings.

        Returns list of (memory_id, similarity, narrative, signal_count) tuples.
        """
        conn = _get_connection()
        # Get all approved and pending_review memories with embeddings
        cursor = conn.execute(
            """SELECT m.id, m.narrative, m.signal_count, m.narrative_embedding
               FROM memories m
               WHERE m.status IN ('approved', 'pending_review')
               AND m.narrative_embedding IS NOT NULL"""
        )

        candidate_embeddings: list[tuple[str, bytes]] = []
        memory_info: dict[str, tuple[str, int]] = {}

        for row in cursor.fetchall():
            memory_id = row["id"]
            candidate_embeddings.append((memory_id, row["narrative_embedding"]))
            memory_info[memory_id] = (row["narrative"], row["signal_count"])

        if not candidate_embeddings:
            return []

        # Find similar via embedding service
        embedding_service = self._get_embedding_service()
        similar = embedding_service.find_similar(
            query_embedding,
            candidate_embeddings,
            threshold=self._similarity_threshold,
            top_k=top_k,
        )

        results = []
        for memory_id, similarity in similar:
            narrative, signal_count = memory_info[memory_id]
            results.append((memory_id, similarity, narrative, signal_count))

        return results

    def _judge_duplicate(
        self, new_narrative: str, existing_narrative: str, signal_count: int
    ) -> DeduplicationResult:
        """Use LLM to judge if two memories are substantively the same."""
        try:
            provider = self._get_provider()
            user_prompt = DEDUP_JUDGMENT_USER.format(
                new_narrative=new_narrative,
                existing_narrative=existing_narrative,
                signal_count=signal_count,
            )

            raw = provider.chat_json(
                system=DEDUP_JUDGMENT_SYSTEM,
                user=user_prompt,
                temperature=0.1,
            )
            parsed = json.loads(raw)

            if not isinstance(parsed, dict):
                return DeduplicationResult(is_duplicate=False, reason="Invalid LLM response")

            is_match = parsed.get("is_match", False)
            return DeduplicationResult(
                is_duplicate=bool(is_match),
                reason=parsed.get("reason", ""),
                merged_narrative=parsed.get("merged_narrative", "") if is_match else "",
            )
        except Exception as e:
            logger.warning("Dedup judgment failed, treating as new: %s", e)
            return DeduplicationResult(is_duplicate=False, reason=f"LLM error: {e}")

    def _reinforce(
        self,
        memory_id: str,
        conversation_id: str,
        *,
        merged_narrative: str = "",
    ) -> Memory:
        """Reinforce an existing memory (increment signal_count).

        Optionally updates the narrative with a merged version.
        Re-enters pending_review so the user sees the reinforcement.
        """
        now = _now_iso()

        with _transaction() as conn:
            # Increment signal_count, update timestamp, re-enter review
            updates = [
                "signal_count = signal_count + 1",
                "last_reinforced_at = ?",
                "status = 'pending_review'",
                "user_reviewed = 0",
            ]
            params: list[Any] = [now]

            if merged_narrative:
                # Save original if not already saved
                conn.execute(
                    """UPDATE memories SET original_narrative = narrative
                       WHERE id = ? AND original_narrative IS NULL""",
                    (memory_id,),
                )
                updates.append("narrative = ?")
                params.append(merged_narrative)

            params.append(memory_id)
            conn.execute(
                f"UPDATE memories SET {', '.join(updates)} WHERE id = ?",
                params,
            )

        # Link the source conversation via graph relationship
        memory = self.get_by_id(memory_id)
        if memory:
            self._link_conversation(memory.block_id, conversation_id)
            logger.info(
                "Reinforced memory %s (signal_count now %d) from conversation %s",
                memory_id,
                memory.signal_count,
                conversation_id,
            )

        return memory  # type: ignore[return-value]

    def _create_memory(
        self,
        conversation_id: str,
        narrative: str,
        *,
        embedding: bytes | None = None,
        model: str = "",
        confidence: float = 0.0,
        destination_act_id: str | None = None,
    ) -> Memory:
        """Create a new memory (no duplicate found)."""
        memory_id = _new_id()
        block_id = f"block-{_new_id()}"
        now = _now_iso()
        is_your_story = destination_act_id is None
        act_id = destination_act_id or YOUR_STORY_ACT_ID

        with _transaction() as conn:
            # Create block
            conn.execute(
                """INSERT INTO blocks (id, type, act_id, parent_id, page_id, scene_id,
                   position, created_at, updated_at)
                   VALUES (?, 'memory', ?, NULL, NULL, NULL, 0, ?, ?)""",
                (block_id, act_id, now, now),
            )

            # Create memory row
            conn.execute(
                """INSERT INTO memories (id, block_id, conversation_id, narrative,
                   narrative_embedding, destination_act_id, is_your_story, status,
                   extraction_model, extraction_confidence, signal_count, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'pending_review', ?, ?, 1, ?)""",
                (
                    memory_id,
                    block_id,
                    conversation_id,
                    narrative,
                    embedding,
                    destination_act_id,
                    1 if is_your_story else 0,
                    model,
                    confidence,
                    now,
                ),
            )

            # Store embedding in block_embeddings if available
            if embedding:
                import hashlib

                content_hash = hashlib.sha256(narrative.encode()).hexdigest()[:16]
                conn.execute(
                    """INSERT INTO block_embeddings (block_id, embedding,
                       embedding_model, content_hash, created_at)
                       VALUES (?, ?, 'all-MiniLM-L6-v2', ?, ?)""",
                    (block_id, embedding, content_hash, now),
                )

        # Link conversation via graph
        self._link_conversation(block_id, conversation_id)

        memory = Memory(
            id=memory_id,
            block_id=block_id,
            conversation_id=conversation_id,
            narrative=narrative,
            destination_act_id=destination_act_id,
            is_your_story=is_your_story,
            status="pending_review",
            signal_count=1,
            last_reinforced_at=None,
            extraction_model=model,
            extraction_confidence=confidence,
            user_reviewed=False,
            user_edited=False,
            original_narrative=None,
            created_at=now,
        )

        logger.info("Created memory %s for conversation %s", memory_id, conversation_id)
        return memory

    def _link_conversation(self, block_id: str, conversation_id: str) -> None:
        """Create MEMORY_OF relationship between memory block and conversation block."""
        try:
            conn = _get_connection()
            cursor = conn.execute(
                "SELECT block_id FROM conversations WHERE id = ?",
                (conversation_id,),
            )
            row = cursor.fetchone()
            if row:
                graph = self._get_graph_store()
                graph.create_relationship(
                    block_id,
                    row["block_id"],
                    RelationshipType.DERIVED_FROM,
                    source=RelationshipSource.CAIRN,
                )
        except Exception as e:
            logger.warning("Failed to link memory to conversation: %s", e)

    # -------------------------------------------------------------------------
    # Review Gate
    # -------------------------------------------------------------------------

    def get_pending_review(self, *, limit: int = 50) -> list[Memory]:
        """Get memories awaiting user review."""
        conn = _get_connection()
        cursor = conn.execute(
            "SELECT * FROM memories WHERE status = 'pending_review' "
            "ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        return [Memory.from_row(row) for row in cursor.fetchall()]

    def approve(self, memory_id: str) -> Memory:
        """Approve a memory (enters the reasoning pool).

        Raises:
            MemoryError: If memory not found or not in pending_review status.
        """
        return self._review_transition(memory_id, "approved")

    def reject(self, memory_id: str) -> Memory:
        """Reject a memory (excluded from reasoning).

        Raises:
            MemoryError: If memory not found or not in pending_review status.
        """
        return self._review_transition(memory_id, "rejected")

    def _review_transition(self, memory_id: str, target_status: str) -> Memory:
        """Transition a memory through the review gate."""
        memory = self.get_by_id(memory_id)
        if not memory:
            raise MemoryError(f"Memory not found: {memory_id}")
        if memory.status != "pending_review":
            raise MemoryError(
                f"Cannot {target_status} memory in '{memory.status}' state "
                f"(must be 'pending_review')"
            )

        with _transaction() as conn:
            conn.execute(
                "UPDATE memories SET status = ?, user_reviewed = 1 WHERE id = ?",
                (target_status, memory_id),
            )

        memory.status = target_status
        memory.user_reviewed = True
        logger.info("Memory %s → %s", memory_id, target_status)
        return memory

    def edit_narrative(self, memory_id: str, new_narrative: str) -> Memory:
        """Edit a memory's narrative (preserves original).

        Can only edit memories in pending_review status.
        """
        memory = self.get_by_id(memory_id)
        if not memory:
            raise MemoryError(f"Memory not found: {memory_id}")
        if memory.status != "pending_review":
            raise MemoryError("Can only edit memories in pending_review status")

        with _transaction() as conn:
            # Preserve original on first edit
            conn.execute(
                """UPDATE memories SET original_narrative = narrative
                   WHERE id = ? AND original_narrative IS NULL""",
                (memory_id,),
            )
            conn.execute(
                "UPDATE memories SET narrative = ?, user_edited = 1 WHERE id = ?",
                (new_narrative, memory_id),
            )

        if memory.original_narrative is None:
            memory.original_narrative = memory.narrative
        memory.narrative = new_narrative
        memory.user_edited = True
        logger.info("Edited narrative for memory %s", memory_id)
        return memory

    # -------------------------------------------------------------------------
    # Routing
    # -------------------------------------------------------------------------

    def route(self, memory_id: str, destination_act_id: str) -> Memory:
        """Route a memory to a specific Act.

        Args:
            memory_id: The memory to route.
            destination_act_id: Target Act ID.

        Raises:
            MemoryError: If memory not found.
        """
        memory = self.get_by_id(memory_id)
        if not memory:
            raise MemoryError(f"Memory not found: {memory_id}")

        is_your_story = destination_act_id == YOUR_STORY_ACT_ID

        with _transaction() as conn:
            conn.execute(
                """UPDATE memories SET destination_act_id = ?, is_your_story = ?
                   WHERE id = ?""",
                (destination_act_id, 1 if is_your_story else 0, memory_id),
            )
            # Update the block's act_id too
            conn.execute(
                "UPDATE blocks SET act_id = ? WHERE id = ?",
                (destination_act_id, memory.block_id),
            )

        memory.destination_act_id = destination_act_id
        memory.is_your_story = is_your_story
        logger.info("Routed memory %s to act %s", memory_id, destination_act_id)
        return memory

    # -------------------------------------------------------------------------
    # Correction & Supersession
    # -------------------------------------------------------------------------

    def supersede(self, old_memory_id: str, new_memory_id: str) -> Memory:
        """Mark a memory as superseded by a newer one.

        The new memory inherits the old memory's signal_count.
        Creates a SUPERSEDES relationship in the graph.

        Raises:
            MemoryError: If either memory not found.
        """
        old = self.get_by_id(old_memory_id)
        new = self.get_by_id(new_memory_id)
        if not old:
            raise MemoryError(f"Old memory not found: {old_memory_id}")
        if not new:
            raise MemoryError(f"New memory not found: {new_memory_id}")

        with _transaction() as conn:
            # Mark old as superseded
            conn.execute(
                "UPDATE memories SET status = 'superseded' WHERE id = ?",
                (old_memory_id,),
            )
            # Inherit signal_count
            conn.execute(
                "UPDATE memories SET signal_count = signal_count + ? WHERE id = ?",
                (old.signal_count, new_memory_id),
            )

        # Create SUPERSEDES relationship
        try:
            graph = self._get_graph_store()
            graph.create_relationship(
                new.block_id,
                old.block_id,
                RelationshipType.SUPERSEDES,
                source=RelationshipSource.USER,
            )
        except Exception as e:
            logger.warning("Failed to create supersedes relationship: %s", e)

        # Return updated new memory
        return self.get_by_id(new_memory_id)  # type: ignore[return-value]

    def correct(
        self,
        memory_id: str,
        corrected_narrative: str,
        conversation_id: str,
    ) -> Memory:
        """Create a correction that supersedes an existing memory.

        Creates a new memory with the corrected narrative, then supersedes the old one.
        The new memory inherits signal_count from the old memory.

        Args:
            memory_id: The memory to correct.
            corrected_narrative: The corrected narrative text.
            conversation_id: The conversation where the correction was made.

        Returns:
            The new corrected Memory.
        """
        old = self.get_by_id(memory_id)
        if not old:
            raise MemoryError(f"Memory not found: {memory_id}")

        # Create the corrected memory
        new_memory = self._create_memory(
            conversation_id=conversation_id,
            narrative=corrected_narrative,
            model=old.extraction_model or "",
            confidence=old.extraction_confidence or 0.0,
            destination_act_id=old.destination_act_id,
        )

        # Supersede old with new
        self.supersede(memory_id, new_memory.id)

        return self.get_by_id(new_memory.id)  # type: ignore[return-value]

    # -------------------------------------------------------------------------
    # Thread Resolution
    # -------------------------------------------------------------------------

    def resolve_thread(
        self,
        memory_id: str,
        delta_id: str,
        *,
        resolution_note: str = "",
    ) -> dict[str, Any]:
        """Mark an open thread (state delta) as resolved.

        Threads are state deltas of type 'waiting_on', 'question_opened', etc.
        that represent open items from a conversation. Resolving marks them
        as applied so they no longer surface as open items.

        Args:
            memory_id: The memory containing the thread.
            delta_id: The specific state delta to resolve.
            resolution_note: Optional note about how it was resolved.

        Returns:
            The updated delta dict.

        Raises:
            MemoryError: If memory or delta not found.
        """
        memory = self.get_by_id(memory_id)
        if not memory:
            raise MemoryError(f"Memory not found: {memory_id}")

        conn = _get_connection()
        cursor = conn.execute(
            "SELECT * FROM memory_state_deltas WHERE id = ? AND memory_id = ?",
            (delta_id, memory_id),
        )
        row = cursor.fetchone()
        if not row:
            raise MemoryError(
                f"State delta {delta_id} not found for memory {memory_id}"
            )

        if row["applied"]:
            raise MemoryError(f"State delta {delta_id} is already resolved")

        now = _now_iso()

        # Update the delta_data JSON with resolution info
        delta_data = json.loads(row["delta_data"])
        delta_data["resolved"] = True
        if resolution_note:
            delta_data["resolution_note"] = resolution_note
        delta_data["resolved_at"] = now

        with _transaction() as tx:
            tx.execute(
                """UPDATE memory_state_deltas
                   SET applied = 1, applied_at = ?, delta_data = ?
                   WHERE id = ?""",
                (now, json.dumps(delta_data), delta_id),
            )

        logger.info("Resolved thread %s in memory %s", delta_id, memory_id)
        return {
            "id": delta_id,
            "memory_id": memory_id,
            "delta_type": row["delta_type"],
            "delta_data": delta_data,
            "applied": True,
            "applied_at": now,
        }

    def get_open_threads(self, *, limit: int = 50) -> list[dict[str, Any]]:
        """Get all unresolved state deltas (open threads).

        Returns state deltas where applied=0, representing open items
        like waiting_on, question_opened, etc.
        """
        conn = _get_connection()
        cursor = conn.execute(
            """SELECT d.*, m.narrative, m.conversation_id
               FROM memory_state_deltas d
               JOIN memories m ON d.memory_id = m.id
               WHERE d.applied = 0
               ORDER BY m.created_at DESC
               LIMIT ?""",
            (limit,),
        )
        return [
            {
                "id": row["id"],
                "memory_id": row["memory_id"],
                "delta_type": row["delta_type"],
                "delta_data": json.loads(row["delta_data"]),
                "narrative": row["narrative"],
                "conversation_id": row["conversation_id"],
            }
            for row in cursor.fetchall()
        ]

    # -------------------------------------------------------------------------
    # Supersession Chain
    # -------------------------------------------------------------------------

    def get_latest_version(self, memory_id: str) -> Memory | None:
        """Follow the supersession chain to find the latest version of a memory.

        If the memory has been superseded, follows SUPERSEDES relationships
        until reaching a non-superseded memory.

        Args:
            memory_id: Starting memory ID.

        Returns:
            The latest non-superseded version, or None if not found.
        """
        memory = self.get_by_id(memory_id)
        if not memory:
            return None

        if memory.status != "superseded":
            return memory

        # Follow the chain via block_relationships
        visited: set[str] = {memory_id}
        current = memory

        for _ in range(20):  # Safety limit
            if current.status != "superseded":
                return current

            # Find what superseded this memory
            conn = _get_connection()
            cursor = conn.execute(
                """SELECT m.id FROM memories m
                   JOIN block_relationships br
                     ON m.block_id = br.source_block_id
                   WHERE br.target_block_id = ?
                     AND br.relationship_type = 'supersedes'""",
                (current.block_id,),
            )
            row = cursor.fetchone()
            if not row or row["id"] in visited:
                # Chain is broken or circular — return current
                return current

            visited.add(row["id"])
            next_memory = self.get_by_id(row["id"])
            if not next_memory:
                return current
            current = next_memory

        return current

    # -------------------------------------------------------------------------
    # Query
    # -------------------------------------------------------------------------

    def get_by_id(self, memory_id: str) -> Memory | None:
        """Get a memory by ID."""
        conn = _get_connection()
        cursor = conn.execute("SELECT * FROM memories WHERE id = ?", (memory_id,))
        row = cursor.fetchone()
        return Memory.from_row(row) if row else None

    def get_by_conversation(self, conversation_id: str) -> list[Memory]:
        """Get all memories for a conversation."""
        conn = _get_connection()
        cursor = conn.execute(
            "SELECT * FROM memories WHERE conversation_id = ? ORDER BY created_at DESC",
            (conversation_id,),
        )
        return [Memory.from_row(row) for row in cursor.fetchall()]

    def list_memories(
        self,
        *,
        status: str | None = None,
        act_id: str | None = None,
        limit: int = 50,
    ) -> list[Memory]:
        """List memories with optional filters."""
        conn = _get_connection()
        conditions = []
        params: list[Any] = []

        if status:
            conditions.append("status = ?")
            params.append(status)
        if act_id:
            conditions.append("(destination_act_id = ? OR (? = ? AND is_your_story = 1))")
            params.extend([act_id, act_id, YOUR_STORY_ACT_ID])

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(limit)

        cursor = conn.execute(
            f"SELECT * FROM memories {where} ORDER BY created_at DESC LIMIT ?",
            params,
        )
        return [Memory.from_row(row) for row in cursor.fetchall()]

    def search(
        self,
        query: str,
        *,
        status: str | None = "approved",
        top_k: int = 10,
        threshold: float = 0.5,
    ) -> list[tuple[Memory, float]]:
        """Search memories by semantic similarity.

        Args:
            query: Search query text.
            status: Filter by status (default: approved only). None for all.
            top_k: Maximum results.
            threshold: Minimum similarity threshold.

        Returns:
            List of (Memory, similarity_score) tuples, sorted by similarity.
        """
        embedding_service = self._get_embedding_service()
        query_embedding = embedding_service.embed(query)
        if not query_embedding:
            return []

        conn = _get_connection()
        status_filter = "AND m.status = ?" if status else ""
        params: list[Any] = []
        if status:
            params.append(status)

        cursor = conn.execute(
            f"""SELECT m.id, m.narrative_embedding
               FROM memories m
               WHERE m.narrative_embedding IS NOT NULL
               AND m.status != 'superseded' {status_filter}""",
            params,
        )

        candidate_embeddings: list[tuple[str, bytes]] = []
        for row in cursor.fetchall():
            candidate_embeddings.append((row["id"], row["narrative_embedding"]))

        if not candidate_embeddings:
            return []

        similar = embedding_service.find_similar(
            query_embedding,
            candidate_embeddings,
            threshold=threshold,
            top_k=top_k,
        )

        results = []
        for memory_id, score in similar:
            memory = self.get_by_id(memory_id)
            if memory:
                results.append((memory, score))

        return results

    def get_entities(self, memory_id: str) -> list[dict[str, Any]]:
        """Get extracted entities for a memory."""
        conn = _get_connection()
        cursor = conn.execute(
            "SELECT * FROM memory_entities WHERE memory_id = ? ORDER BY created_at",
            (memory_id,),
        )
        return [
            {
                "id": row["id"],
                "entity_type": row["entity_type"],
                "entity_data": json.loads(row["entity_data"]),
            }
            for row in cursor.fetchall()
        ]

    def get_state_deltas(self, memory_id: str) -> list[dict[str, Any]]:
        """Get state deltas for a memory."""
        conn = _get_connection()
        cursor = conn.execute(
            "SELECT * FROM memory_state_deltas WHERE memory_id = ?",
            (memory_id,),
        )
        return [
            {
                "id": row["id"],
                "delta_type": row["delta_type"],
                "delta_data": json.loads(row["delta_data"]),
            }
            for row in cursor.fetchall()
        ]


def log_memory_influence(
    classification_id: str,
    memory_references: list[dict[str, Any]],
) -> None:
    """Record which memories influenced a classification decision.

    Args:
        classification_id: The operation/classification ID.
        memory_references: List of dicts with keys:
            - memory_id: str
            - influence_type: str ("semantic_match", "graph_expansion", etc.)
            - influence_score: float (0.0 to 1.0)
            - reasoning: str (why this memory was relevant)
    """
    if not memory_references:
        return

    try:
        with _transaction() as conn:
            for ref in memory_references:
                ref_id = _new_id()
                conn.execute(
                    """INSERT INTO classification_memory_references
                       (id, classification_id, memory_id, influence_type,
                        influence_score, reasoning)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        ref_id,
                        classification_id,
                        ref["memory_id"],
                        ref.get("influence_type", "semantic_match"),
                        ref.get("influence_score", 0.0),
                        ref.get("reasoning", ""),
                    ),
                )
    except Exception as e:
        logger.warning("Failed to log memory influence: %s", e)


class MemoryError(Exception):
    """Raised when a memory operation fails."""
