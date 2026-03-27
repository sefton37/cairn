"""Archive Service - LLM-driven conversation archival with knowledge extraction.

Provides:
- Full conversation archival with summaries
- LLM-driven knowledge extraction and categorization
- Automatic act/scene linking detection
- Quality assessment and learning from user feedback
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from ..db import Database
from ..providers import get_provider
from .memory_service import MemoryService

logger = logging.getLogger(__name__)


# LLM Prompts for archival tasks
ARCHIVE_ANALYSIS_PROMPT = """You are analyzing a conversation to create a comprehensive archive with knowledge extraction.

Your tasks:
1. Create a concise TITLE (5-10 words) that captures the main topic
2. Write a brief SUMMARY (2-3 sentences) of what was discussed/accomplished
3. Determine which ACT this conversation most relates to (if any)
4. Extract valuable KNOWLEDGE entries for long-term memory

AVAILABLE ACTS (choose the most relevant one, or null if none fit):
{acts_context}

KNOWLEDGE EXTRACTION RULES:
- Extract facts, lessons, decisions, preferences, and observations
- Be concise - each entry should be 1-2 sentences max
- Focus on durable, actionable knowledge
- Skip trivial or ephemeral details
- Maximum 10 entries total

Return JSON in this exact format:
{{
  "title": "Brief descriptive title",
  "summary": "2-3 sentence summary of the conversation",
  "linked_act_id": "act_id_or_null",
  "linking_reason": "Why this act was chosen (or null)",
  "knowledge_entries": [
    {{"category": "fact", "content": "Specific factual information learned"}},
    {{"category": "lesson", "content": "Insight or lesson from the conversation"}},
    {{"category": "decision", "content": "Decision made about approach or tools"}},
    {{"category": "preference", "content": "User preference expressed"}},
    {{"category": "observation", "content": "Notable pattern or behavior"}}
  ],
  "topics": ["topic1", "topic2"],
  "sentiment": "positive|neutral|negative|mixed"
}}
"""

ASSESS_ARCHIVE_PROMPT = """You are evaluating the quality of an archive extraction.

ORIGINAL CONVERSATION:
{conversation}

ARCHIVE CREATED:
- Title: {title}
- Summary: {summary}
- Linked Act: {linked_act}
- Knowledge Entries: {knowledge_entries}

Rate the archive quality on these dimensions (1-5 scale):
1. TITLE_QUALITY: Does the title accurately capture the main topic?
2. SUMMARY_QUALITY: Is the summary comprehensive but concise?
3. ACT_LINKING: Is the act link appropriate (or correctly left null)?
4. KNOWLEDGE_RELEVANCE: Are the extracted entries valuable and non-trivial?
5. KNOWLEDGE_COVERAGE: Were important insights captured?
6. DEDUPLICATION: Are entries distinct (no redundancy)?

Return JSON:
{{
  "title_quality": 1-5,
  "summary_quality": 1-5,
  "act_linking": 1-5,
  "knowledge_relevance": 1-5,
  "knowledge_coverage": 1-5,
  "deduplication": 1-5,
  "overall_score": 1-5,
  "suggestions": ["improvement suggestion 1", "improvement suggestion 2"]
}}
"""


@dataclass
class ArchiveResult:
    """Result of archiving a conversation."""

    archive_id: str
    title: str
    summary: str
    message_count: int
    linked_act_id: str | None
    linking_reason: str | None
    knowledge_entries_added: int
    topics: list[str]
    archived_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "archive_id": self.archive_id,
            "title": self.title,
            "summary": self.summary,
            "message_count": self.message_count,
            "linked_act_id": self.linked_act_id,
            "linking_reason": self.linking_reason,
            "knowledge_entries_added": self.knowledge_entries_added,
            "topics": self.topics,
            "archived_at": self.archived_at,
        }


@dataclass
class ArchivePreview:
    """Preview of archive analysis before saving."""

    title: str
    summary: str
    linked_act_id: str | None
    linking_reason: str | None
    knowledge_entries: list[dict[str, str]]
    topics: list[str]
    message_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "summary": self.summary,
            "linked_act_id": self.linked_act_id,
            "linking_reason": self.linking_reason,
            "knowledge_entries": self.knowledge_entries,
            "topics": self.topics,
            "message_count": self.message_count,
        }


@dataclass
class ArchiveQualityAssessment:
    """Quality assessment of an archive."""

    assessment_id: str
    archive_id: str
    title_quality: int
    summary_quality: int
    act_linking: int
    knowledge_relevance: int
    knowledge_coverage: int
    deduplication: int
    overall_score: int
    suggestions: list[str]
    user_feedback: str | None = None
    user_rating: int | None = None
    assessed_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "assessment_id": self.assessment_id,
            "archive_id": self.archive_id,
            "title_quality": self.title_quality,
            "summary_quality": self.summary_quality,
            "act_linking": self.act_linking,
            "knowledge_relevance": self.knowledge_relevance,
            "knowledge_coverage": self.knowledge_coverage,
            "deduplication": self.deduplication,
            "overall_score": self.overall_score,
            "suggestions": self.suggestions,
            "user_feedback": self.user_feedback,
            "user_rating": self.user_rating,
            "assessed_at": self.assessed_at,
        }


class ArchiveService:
    """Service for LLM-driven conversation archival."""

    def __init__(self, db: Database):
        self._db = db
        self._mem_service = MemoryService()

    def preview_archive(
        self,
        conversation_id: str,
        *,
        auto_link: bool = True,
    ) -> ArchivePreview:
        """Preview what will be extracted before archiving.

        Runs LLM analysis without saving anything. Returns a preview
        that can be reviewed and modified before calling archive_with_review.

        Args:
            conversation_id: The conversation to analyze
            auto_link: If True, LLM will suggest act link

        Returns:
            ArchivePreview with analysis results
        """
        # Get conversation messages
        messages = self._db.get_messages(conversation_id=conversation_id, limit=500)
        if not messages:
            raise ValueError("No messages in conversation")

        formatted_messages = [
            {
                "role": m["role"],
                "content": m["content"],
                "created_at": m.get("created_at", ""),
            }
            for m in messages
        ]

        # Get acts context for LLM linking
        acts_context = self._get_acts_context() if auto_link else "N/A"

        # Run LLM analysis
        analysis = self._analyze_conversation(formatted_messages, acts_context)

        return ArchivePreview(
            title=analysis.get("title", f"Conversation {datetime.now(UTC).isoformat()[:10]}"),
            summary=analysis.get("summary", ""),
            linked_act_id=analysis.get("linked_act_id"),
            linking_reason=analysis.get("linking_reason"),
            knowledge_entries=analysis.get("knowledge_entries", []),
            topics=analysis.get("topics", []),
            message_count=len(messages),
        )

    def archive_with_review(
        self,
        conversation_id: str,
        *,
        title: str,
        summary: str,
        act_id: str | None = None,
        knowledge_entries: list[dict[str, str]],
        additional_notes: str = "",
        rating: int | None = None,
    ) -> ArchiveResult:
        """Archive a conversation with user-reviewed data.

        Called after preview_archive when user has reviewed and approved.

        Args:
            conversation_id: The conversation to archive
            title: User-approved/edited title
            summary: User-approved/edited summary
            act_id: The act to link to (user-approved)
            knowledge_entries: User-approved knowledge entries
            additional_notes: Additional notes from user
            rating: User's quality rating (1-5) for learning

        Returns:
            ArchiveResult with archive details
        """
        # Get conversation messages (just to validate they exist)
        messages = self._db.get_messages(conversation_id=conversation_id, limit=500)
        if not messages:
            raise ValueError("No messages in conversation")

        # Generate archive_id and metadata (messages already stored in DB)
        archive_id = uuid.uuid4().hex[:12]
        now = datetime.now(UTC).isoformat()

        # Store archive metadata in database
        self._store_archive_metadata(
            archive_id=archive_id,
            conversation_id=conversation_id,
            act_id=act_id,
            linking_reason=None,  # User approved, no need for reason
            topics=[],
            sentiment="neutral",
        )

        # Add user-approved knowledge entries as memories
        knowledge_added = 0
        source_tag = f"archive_service:{archive_id}"
        if knowledge_entries:
            for entry in knowledge_entries:
                try:
                    self._mem_service.store(
                        conversation_id=conversation_id,
                        narrative=entry["content"],
                        destination_act_id=act_id,
                        source=source_tag,
                        memory_type=entry.get("category", "observation"),
                        status="approved",
                    )
                    knowledge_added += 1
                except Exception:
                    logger.debug(
                        "Failed to store learned entry: %s",
                        entry.get("content", "")[:50],
                    )

        # If user provided additional notes, add them as observations
        if additional_notes.strip():
            try:
                self._mem_service.store(
                    conversation_id=conversation_id,
                    narrative=additional_notes.strip(),
                    destination_act_id=act_id,
                    source=source_tag,
                    memory_type="observation",
                    status="approved",
                )
                knowledge_added += 1
            except Exception:
                logger.debug("Failed to store additional notes as memory")

        # If user provided a rating, store it for learning
        if rating is not None:
            self.submit_user_feedback(archive_id, rating)

        return ArchiveResult(
            archive_id=archive_id,
            title=title,
            summary=summary,
            message_count=len(messages),
            linked_act_id=act_id,
            linking_reason=None,
            knowledge_entries_added=knowledge_added,
            topics=[],
            archived_at=now,
        )

    def archive_conversation(
        self,
        conversation_id: str,
        *,
        act_id: str | None = None,
        auto_link: bool = True,
        extract_knowledge: bool = True,
    ) -> ArchiveResult:
        """Archive a conversation with LLM-driven analysis.

        Args:
            conversation_id: The conversation to archive
            act_id: Optional explicit act to link to (overrides auto-detection)
            auto_link: If True and act_id not provided, LLM will suggest act link
            extract_knowledge: If True, extract knowledge entries

        Returns:
            ArchiveResult with archive details
        """
        # Get conversation messages
        messages = self._db.get_messages(conversation_id=conversation_id, limit=500)
        if not messages:
            raise ValueError("No messages in conversation")

        formatted_messages = [
            {
                "role": m["role"],
                "content": m["content"],
                "created_at": m.get("created_at", ""),
            }
            for m in messages
        ]

        # Get acts context for LLM linking
        acts_context = self._get_acts_context() if auto_link and not act_id else "N/A"

        # Run LLM analysis
        analysis = self._analyze_conversation(formatted_messages, acts_context)

        # Determine final act_id
        final_act_id = act_id
        linking_reason = None
        if not act_id and auto_link and analysis.get("linked_act_id"):
            final_act_id = analysis["linked_act_id"]
            linking_reason = analysis.get("linking_reason")

        # Generate archive_id and metadata (messages already stored in DB)
        archive_id = uuid.uuid4().hex[:12]
        archive_title = analysis.get("title", f"Conversation {datetime.now(UTC).isoformat()[:10]}")
        archive_summary = analysis.get("summary", "")
        now = datetime.now(UTC).isoformat()

        # Store archive metadata in database
        self._store_archive_metadata(
            archive_id=archive_id,
            conversation_id=conversation_id,
            act_id=final_act_id,
            linking_reason=linking_reason,
            topics=analysis.get("topics", []),
            sentiment=analysis.get("sentiment", "neutral"),
        )

        # Extract and store knowledge if enabled
        knowledge_added = 0
        source_tag = f"archive_service:{archive_id}"
        if extract_knowledge and analysis.get("knowledge_entries"):
            for entry in analysis["knowledge_entries"]:
                try:
                    self._mem_service.store(
                        conversation_id=conversation_id,
                        narrative=entry["content"],
                        destination_act_id=final_act_id,
                        source=source_tag,
                        memory_type=entry.get("category", "observation"),
                        status="approved",
                    )
                    knowledge_added += 1
                except Exception:
                    logger.debug(
                        "Failed to store learned entry: %s",
                        entry.get("content", "")[:50],
                    )

        return ArchiveResult(
            archive_id=archive_id,
            title=archive_title,
            summary=archive_summary,
            message_count=len(messages),
            linked_act_id=final_act_id,
            linking_reason=linking_reason,
            knowledge_entries_added=knowledge_added,
            topics=analysis.get("topics", []),
            archived_at=now,
        )

    def delete_conversation(
        self,
        conversation_id: str,
        *,
        archive_first: bool = False,
    ) -> dict[str, Any]:
        """Delete a conversation, optionally archiving first.

        Args:
            conversation_id: The conversation to delete
            archive_first: If True, archive before deleting

        Returns:
            Dict with deletion result
        """
        archive_id = None

        if archive_first:
            result = self.archive_conversation(conversation_id)
            archive_id = result.archive_id

        # Delete messages
        self._db.clear_messages(conversation_id=conversation_id)

        # Delete conversation record
        conn = self._db.connect()
        conn.execute(
            "DELETE FROM conversations WHERE id = ?",
            (conversation_id,),
        )
        conn.commit()

        return {
            "deleted": True,
            "conversation_id": conversation_id,
            "archive_id": archive_id,
        }

    def assess_archive_quality(
        self,
        archive_id: str,
        act_id: str | None = None,
    ) -> ArchiveQualityAssessment:
        """Assess the quality of an archive using LLM.

        Args:
            archive_id: The archive to assess
            act_id: The act the archive is in (or None for play level)

        Returns:
            ArchiveQualityAssessment with scores and suggestions
        """
        archive_meta = self._get_archive_metadata(archive_id)
        if not archive_meta:
            raise ValueError(f"Archive not found: {archive_id}")

        # Get messages for this archive via the linked conversation
        linked_conv_id = archive_meta.get("conversation_id")
        messages: list[dict[str, Any]] = []
        if linked_conv_id:
            raw_messages = self._db.get_messages(conversation_id=linked_conv_id, limit=500)
            messages = [
                {"role": m["role"], "content": m["content"]}
                for m in raw_messages
            ]

        # Format conversation for assessment
        conversation_text = self._format_messages(messages)

        # Determine act from metadata
        resolved_act_id = archive_meta.get("act_id") or act_id

        # Get linked act name
        linked_act = "None"
        if resolved_act_id:
            from ..play_fs import list_acts
            acts_list = list_acts()
            for act in acts_list:
                if act.get("act_id") == resolved_act_id:
                    linked_act = act.get("title", resolved_act_id)
                    break

        # Get knowledge entries stored for this archive (source tagged with archive_id)
        source_tag = f"archive_service:{archive_id}"
        conn = self._db.connect()
        cursor = conn.execute(
            "SELECT memory_type, narrative FROM memories WHERE source = ?",
            (source_tag,),
        )
        related_rows = cursor.fetchall()
        knowledge_text = "\n".join(
            f"- [{row['memory_type'] or 'observation'}] {row['narrative']}"
            for row in related_rows
        ) or "None extracted"

        # Get title and summary from archive_metadata (stored as JSON topics/linking_reason)
        # Title and summary are not stored in archive_metadata — use archive_id as fallback
        archive_title = archive_id
        archive_summary = ""
        # Try to get title/summary from the assessment context (best effort)
        conn2 = self._db.connect()
        cur2 = conn2.execute(
            "SELECT linking_reason FROM archive_metadata WHERE archive_id = ?",
            (archive_id,),
        )
        row2 = cur2.fetchone()
        if row2 and row2["linking_reason"]:
            archive_summary = row2["linking_reason"]

        # Run LLM assessment
        prompt = ASSESS_ARCHIVE_PROMPT.format(
            conversation=conversation_text[:4000],  # Truncate for context
            title=archive_title,
            summary=archive_summary,
            linked_act=linked_act,
            knowledge_entries=knowledge_text,
        )

        try:
            provider = get_provider(self._db)
            response = provider.chat_text(
                system="You are an archive quality assessor. Return only valid JSON.",
                user=prompt,
                temperature=0.3,
            )

            data = json.loads(response)

            assessment = ArchiveQualityAssessment(
                assessment_id=uuid.uuid4().hex[:12],
                archive_id=archive_id,
                title_quality=data.get("title_quality", 3),
                summary_quality=data.get("summary_quality", 3),
                act_linking=data.get("act_linking", 3),
                knowledge_relevance=data.get("knowledge_relevance", 3),
                knowledge_coverage=data.get("knowledge_coverage", 3),
                deduplication=data.get("deduplication", 3),
                overall_score=data.get("overall_score", 3),
                suggestions=data.get("suggestions", []),
                assessed_at=datetime.now(UTC).isoformat(),
            )

            # Store assessment
            self._store_assessment(assessment)

            return assessment

        except (json.JSONDecodeError, Exception) as e:
            logger.warning("Failed to assess archive: %s", e)
            # Return default assessment
            return ArchiveQualityAssessment(
                assessment_id=uuid.uuid4().hex[:12],
                archive_id=archive_id,
                title_quality=3,
                summary_quality=3,
                act_linking=3,
                knowledge_relevance=3,
                knowledge_coverage=3,
                deduplication=3,
                overall_score=3,
                suggestions=["Assessment failed - using defaults"],
                assessed_at=datetime.now(UTC).isoformat(),
            )

    def submit_user_feedback(
        self,
        archive_id: str,
        rating: int,
        feedback: str | None = None,
    ) -> dict[str, Any]:
        """Submit user feedback on archive quality.

        Args:
            archive_id: The archive being rated
            rating: 1-5 star rating
            feedback: Optional text feedback

        Returns:
            Confirmation dict
        """
        conn = self._db.connect()
        now = datetime.now(UTC).isoformat()

        # Store feedback
        feedback_id = uuid.uuid4().hex[:12]
        conn.execute(
            """
            INSERT INTO archive_feedback
            (id, archive_id, rating, feedback, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (feedback_id, archive_id, rating, feedback, now),
        )
        conn.commit()

        return {
            "feedback_id": feedback_id,
            "archive_id": archive_id,
            "rating": rating,
            "submitted_at": now,
        }

    def get_learning_stats(self) -> dict[str, Any]:
        """Get statistics about archival learning/quality.

        Returns:
            Dict with quality stats over time
        """
        conn = self._db.connect()

        # Average user ratings
        cursor = conn.execute(
            """
            SELECT
                COUNT(*) as total_feedback,
                AVG(rating) as avg_rating,
                MIN(rating) as min_rating,
                MAX(rating) as max_rating
            FROM archive_feedback
            """
        )
        row = cursor.fetchone()

        # Recent assessments
        cursor = conn.execute(
            """
            SELECT
                COUNT(*) as total_assessments,
                AVG(overall_score) as avg_score
            FROM archive_assessments
            WHERE assessed_at > datetime('now', '-30 days')
            """
        )
        assess_row = cursor.fetchone()

        return {
            "total_user_feedback": row["total_feedback"] if row else 0,
            "avg_user_rating": round(row["avg_rating"], 2) if row and row["avg_rating"] else 0,
            "total_assessments": assess_row["total_assessments"] if assess_row else 0,
            "avg_assessment_score": round(assess_row["avg_score"], 2) if assess_row and assess_row["avg_score"] else 0,
        }

    def list_archives(
        self,
        act_id: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List archives with metadata.

        Args:
            act_id: Filter by act (None for all)
            limit: Maximum results

        Returns:
            List of archive metadata dicts
        """
        conn = self._db.connect()
        if act_id is not None:
            cursor = conn.execute(
                """SELECT
                       m.archive_id, m.act_id, m.conversation_id,
                       m.linking_reason, m.topics, m.sentiment, m.created_at,
                       (SELECT AVG(rating) FROM archive_feedback WHERE archive_id = m.archive_id) as avg_rating
                   FROM archive_metadata m
                   WHERE m.act_id = ?
                   ORDER BY m.created_at DESC
                   LIMIT ?""",
                (act_id, limit),
            )
        else:
            cursor = conn.execute(
                """SELECT
                       m.archive_id, m.act_id, m.conversation_id,
                       m.linking_reason, m.topics, m.sentiment, m.created_at,
                       (SELECT AVG(rating) FROM archive_feedback WHERE archive_id = m.archive_id) as avg_rating
                   FROM archive_metadata m
                   ORDER BY m.created_at DESC
                   LIMIT ?""",
                (limit,),
            )

        results = []
        for row in cursor.fetchall():
            # Get message count from the linked conversation
            msg_count = 0
            if row["conversation_id"]:
                cur2 = conn.execute(
                    "SELECT COUNT(*) as cnt FROM messages WHERE conversation_id = ?",
                    (row["conversation_id"],),
                )
                cnt_row = cur2.fetchone()
                if cnt_row:
                    msg_count = cnt_row["cnt"]

            results.append({
                "archive_id": row["archive_id"],
                "act_id": row["act_id"],
                "title": row["archive_id"],  # title not stored in metadata
                "summary": row["linking_reason"] or "",
                "message_count": msg_count,
                "created_at": row["created_at"],
                "archived_at": row["created_at"],
                "topics": json.loads(row["topics"]) if row["topics"] else [],
                "sentiment": row["sentiment"],
                "user_rating": row["avg_rating"],
            })

        return results

    def get_archive(
        self,
        archive_id: str,
        act_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Get a specific archive with full details.

        Args:
            archive_id: The archive ID
            act_id: The act it's in (or None for play level)

        Returns:
            Archive dict with messages, or None if not found
        """
        metadata = self._get_archive_metadata(archive_id)
        if not metadata:
            return None

        # Get messages via the linked conversation
        messages: list[dict[str, Any]] = []
        linked_conv_id = metadata.get("conversation_id")
        if linked_conv_id:
            raw_messages = self._db.get_messages(conversation_id=linked_conv_id, limit=500)
            messages = [
                {
                    "role": m["role"],
                    "content": m["content"],
                    "created_at": m.get("created_at", ""),
                }
                for m in raw_messages
            ]

        return {
            "archive_id": archive_id,
            "act_id": metadata.get("act_id"),
            "title": archive_id,  # title not stored in metadata
            "summary": metadata.get("linking_reason") or "",
            "message_count": len(messages),
            "messages": messages,
            "created_at": metadata.get("created_at") or "",
            "archived_at": metadata.get("created_at") or "",
            "topics": metadata.get("topics", []),
            "sentiment": metadata.get("sentiment"),
            "linking_reason": metadata.get("linking_reason"),
        }

    # --- Private Methods ---

    def _analyze_conversation(
        self,
        messages: list[dict[str, Any]],
        acts_context: str,
    ) -> dict[str, Any]:
        """Use LLM to analyze conversation for archival."""
        conversation_text = self._format_messages(messages)

        prompt = ARCHIVE_ANALYSIS_PROMPT.format(acts_context=acts_context)

        try:
            provider = get_provider(self._db)
            response = provider.chat_text(
                system=prompt,
                user=f"CONVERSATION TO ARCHIVE:\n\n{conversation_text}",
                temperature=0.3,
            )

            # Parse JSON response
            data = json.loads(response)
            return data

        except (json.JSONDecodeError, Exception) as e:
            logger.warning("Failed to analyze conversation: %s", e)
            # Return minimal analysis
            return {
                "title": f"Conversation {datetime.now(UTC).isoformat()[:10]}",
                "summary": "",
                "linked_act_id": None,
                "knowledge_entries": [],
                "topics": [],
                "sentiment": "neutral",
            }

    def _format_messages(self, messages: list[dict[str, Any]]) -> str:
        """Format messages for LLM analysis."""
        lines = []
        for msg in messages:
            role = str(msg.get("role", "unknown")).upper()
            content = str(msg.get("content", ""))
            # Truncate very long messages
            if len(content) > 2000:
                content = content[:2000] + "... [truncated]"
            lines.append(f"{role}: {content}")
            lines.append("")
        return "\n".join(lines)

    def _get_acts_context(self) -> str:
        """Get formatted acts list for LLM context."""
        from ..play_fs import list_acts

        acts = list_acts()
        if not acts:
            return "No acts defined"

        lines = []
        for act in acts:
            act_id = act.get("act_id", "")
            title = act.get("title", "Untitled")
            notes = act.get("notes", "")[:100]
            active = " (ACTIVE)" if act.get("active") else ""
            lines.append(f"- {act_id}: {title}{active}")
            if notes:
                lines.append(f"  Notes: {notes}")

        return "\n".join(lines)

    def _store_archive_metadata(
        self,
        archive_id: str,
        conversation_id: str,
        act_id: str | None,
        linking_reason: str | None,
        topics: list[str],
        sentiment: str,
    ) -> None:
        """Store archive metadata in database."""
        conn = self._db.connect()
        now = datetime.now(UTC).isoformat()

        conn.execute(
            """
            INSERT OR REPLACE INTO archive_metadata
            (archive_id, conversation_id, act_id, linking_reason, topics, sentiment, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                archive_id,
                conversation_id,
                act_id,
                linking_reason,
                json.dumps(topics),
                sentiment,
                now,
            ),
        )
        conn.commit()

    def _get_archive_metadata(self, archive_id: str) -> dict[str, Any] | None:
        """Get archive metadata from database."""
        conn = self._db.connect()

        cursor = conn.execute(
            """
            SELECT
                m.*,
                (SELECT AVG(rating) FROM archive_feedback WHERE archive_id = m.archive_id) as avg_rating
            FROM archive_metadata m
            WHERE m.archive_id = ?
            """,
            (archive_id,),
        )
        row = cursor.fetchone()

        if not row:
            return None

        return {
            "archive_id": row["archive_id"],
            "conversation_id": row["conversation_id"],
            "act_id": row["act_id"],
            "linking_reason": row["linking_reason"],
            "topics": json.loads(row["topics"]) if row["topics"] else [],
            "sentiment": row["sentiment"],
            "avg_rating": row["avg_rating"],
        }

    def _store_assessment(self, assessment: ArchiveQualityAssessment) -> None:
        """Store quality assessment in database."""
        conn = self._db.connect()

        conn.execute(
            """
            INSERT INTO archive_assessments
            (id, archive_id, title_quality, summary_quality, act_linking,
             knowledge_relevance, knowledge_coverage, deduplication,
             overall_score, suggestions, assessed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                assessment.assessment_id,
                assessment.archive_id,
                assessment.title_quality,
                assessment.summary_quality,
                assessment.act_linking,
                assessment.knowledge_relevance,
                assessment.knowledge_coverage,
                assessment.deduplication,
                assessment.overall_score,
                json.dumps(assessment.suggestions),
                assessment.assessed_at,
            ),
        )
        conn.commit()
