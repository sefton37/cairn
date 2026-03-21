"""Email Intelligence Service for CAIRN.

Syncs email metadata from Thunderbird's Gloda database, generates embeddings,
scores importance, and surfaces important unread emails in the attention pane.

SECURITY ARCHITECTURE — The Isolation Barrier:

    UNTRUSTED ZONE (email content from Thunderbird)
    ├── Body text → sentence-transformers → 384-dim vector (opaque)
    ├── Subject → detect_prompt_injection() → sanitized or hidden
    └── Structured metadata → always safe

    ═══════════ HARD BARRIER ═══════════

    TRUSTED ZONE (safe for LLM reasoning)
    ├── Structured metadata (sender, date, flags)
    ├── Sanitized subjects (post-injection-check)
    ├── Computed scores (numbers only)
    └── Embedding similarity scores (numbers only)

Email body text NEVER enters an LLM context window. The embedding model
(sentence-transformers) is the only code that processes body text.
"""

from __future__ import annotations

import json
import logging
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from cairn.cairn.store import CairnStore
    from cairn.cairn.thunderbird import ThunderbirdBridge

logger = logging.getLogger(__name__)


# =============================================================================
# Data Types
# =============================================================================


@dataclass
class EmailImportanceResult:
    """Result of importance scoring for a single email."""

    gloda_message_id: int
    importance_score: float
    people_score: float
    play_score: float
    behavioral_score: float
    notability_score: float
    urgency: str  # "high", "medium", "low"
    reason: str


# Importance scoring weights
DEFAULT_WEIGHTS = {
    "people": 0.35,
    "play": 0.25,
    "behavioral": 0.30,
    "notability": 0.10,
}


# =============================================================================
# Email Intelligence Service
# =============================================================================


class EmailIntelligenceService:
    """Orchestrates email intelligence: sync, embed, score, surface.

    This service bridges Thunderbird's Gloda database and CAIRN's attention
    system. It maintains the isolation barrier between untrusted email content
    and the trusted LLM zone.
    """

    def __init__(
        self,
        cairn_store: "CairnStore",
        thunderbird: "ThunderbirdBridge",
        weights: dict[str, float] | None = None,
    ):
        self.store = cairn_store
        self.thunderbird = thunderbird
        self.weights = weights or DEFAULT_WEIGHTS.copy()

    # =========================================================================
    # Sync: Gloda → email_cache
    # =========================================================================

    def sync_emails(self, *, since: datetime | None = None, limit: int = 1000) -> int:
        """Sync metadata from Gloda → email_cache. Sanitize subjects. Update profiles.

        Returns:
            Number of emails synced.
        """
        from cairn.security import detect_prompt_injection

        if not self.thunderbird.has_email_db():
            return 0

        # Determine sync window
        if since is None:
            since = self._get_last_sync_time()

        messages = self.thunderbird.list_email_messages(since=since, limit=limit)

        # Supplement Gloda with mbox reads for IMAP accounts (Gmail, Outlook.com)
        # that Gloda under-indexes. Load stored byte offsets, pass as offset_store
        # so the bridge can track incremental progress, then flush them back.
        offset_store = self._load_mbox_offsets()
        mbox_messages = self.thunderbird.list_email_messages_from_mbox(
            since=since,
            limit=limit,
            _offset_store=offset_store,
        )
        self._flush_mbox_offsets(offset_store)

        # Gloda takes precedence: drop any mbox message whose header_message_id
        # already appears in the Gloda result set (richer notability/threading data).
        gloda_mids: set[str] = {m.header_message_id for m in messages if m.header_message_id}
        for mbox_msg in mbox_messages:
            if mbox_msg.header_message_id not in gloda_mids:
                messages.append(mbox_msg)

        if not messages:
            return 0

        now = datetime.now().isoformat()
        synced = 0

        conn = self.store._get_connection()
        for msg in messages:
            # Sanitize subject via injection detection
            injection_result = detect_prompt_injection(msg.subject)
            if injection_result.is_suspicious:
                sanitized_subject = "[Subject hidden - external content]"
                subject_suspicious = 1
            else:
                sanitized_subject = msg.subject
                subject_suspicious = 0

            # Check if already cached (for read-state change detection)
            existing = conn.execute(
                "SELECT is_read, read_state_changed_at FROM email_cache "
                "WHERE gloda_message_id = ?",
                (msg.id,),
            ).fetchone()

            read_state_changed_at = None
            if existing:
                # Detect read state change
                was_read = bool(existing["is_read"])
                if not was_read and msg.is_read:
                    read_state_changed_at = now

                # Update existing record
                conn.execute(
                    """UPDATE email_cache SET
                        is_read = ?, is_starred = ?, is_replied = ?,
                        is_forwarded = ?, last_synced_at = ?,
                        read_state_changed_at = COALESCE(?, read_state_changed_at),
                        header_message_id = COALESCE(?, header_message_id),
                        account_email = COALESCE(NULLIF(?, ''), account_email, '')
                    WHERE gloda_message_id = ?""",
                    (
                        int(msg.is_read),
                        int(msg.is_starred),
                        int(msg.is_replied),
                        int(msg.is_forwarded),
                        now,
                        read_state_changed_at,
                        msg.header_message_id or None,
                        msg.account_email,
                        msg.id,
                    ),
                )
            else:
                # Insert new record
                conn.execute(
                    """INSERT OR IGNORE INTO email_cache (
                        gloda_message_id, folder_name, account_email,
                        subject, sanitized_subject,
                        subject_is_suspicious, sender_name, sender_email,
                        recipients_json, date, is_read, is_starred, is_replied,
                        is_forwarded, has_attachments, notability,
                        first_seen_at, last_synced_at, header_message_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        msg.id,
                        msg.folder_name,
                        msg.account_email,
                        msg.subject,
                        sanitized_subject,
                        subject_suspicious,
                        msg.sender_name,
                        msg.sender_email,
                        json.dumps(msg.recipients),
                        msg.date.isoformat(),
                        int(msg.is_read),
                        int(msg.is_starred),
                        int(msg.is_replied),
                        int(msg.is_forwarded),
                        int(msg.has_attachments),
                        msg.notability,
                        now,
                        now,
                        msg.header_message_id or None,
                    ),
                )

            synced += 1

        conn.commit()

        # Update sync timestamp
        self._set_sync_state("last_sync", now)

        return synced

    # =========================================================================
    # Embed: Generate embeddings for cached emails
    # =========================================================================

    def embed_emails(self, *, batch_size: int = 50, limit: int = 200) -> int:
        """Generate embeddings for emails missing them.

        SECURITY: Body text → sentence-transformers ONLY. The text is fetched,
        embedded, and immediately discarded. No body text is stored or passed
        to any LLM.

        Returns:
            Number of emails embedded.
        """
        from cairn.memory.embeddings import get_embedding_service

        embedding_service = get_embedding_service()
        if not embedding_service.is_available:
            logger.warning("Embedding service unavailable, skipping email embedding")
            return 0

        conn = self.store._get_connection()

        # Find emails needing embeddings
        cursor = conn.execute(
            """SELECT gloda_message_id, sanitized_subject
            FROM email_cache
            WHERE body_embedding IS NULL
            ORDER BY date DESC
            LIMIT ?""",
            (limit,),
        )
        rows = cursor.fetchall()
        if not rows:
            return 0

        embedded = 0
        for batch_start in range(0, len(rows), batch_size):
            batch = rows[batch_start : batch_start + batch_size]
            msg_ids = [r["gloda_message_id"] for r in batch]

            # SECURITY BARRIER: Fetch body text from Gloda
            body_texts = self.thunderbird.get_email_body_texts_batch(msg_ids)

            for row in batch:
                msg_id = row["gloda_message_id"]
                subject = row["sanitized_subject"] or ""

                # Embed subject (safe — already sanitized)
                subject_emb = embedding_service.embed(subject) if subject else None

                # SECURITY BARRIER: Body text → embedding → discard text
                body_text = body_texts.get(msg_id)
                body_emb = None
                if body_text:
                    body_emb = embedding_service.embed(body_text)
                    # body_text goes out of scope here — never stored

                conn.execute(
                    """UPDATE email_cache SET
                        subject_embedding = ?, body_embedding = ?,
                        embedding_model = ?
                    WHERE gloda_message_id = ?""",
                    (subject_emb, body_emb, embedding_service.model_name, msg_id),
                )
                embedded += 1

        conn.commit()
        return embedded

    # =========================================================================
    # Score: Importance computation
    # =========================================================================

    def score_importance(self, *, limit: int = 100) -> list[EmailImportanceResult]:
        """Score unread emails using people + play + behavioral + notability signals.

        Returns:
            List of scored emails.
        """
        conn = self.store._get_connection()

        # Get emails from the scoring window (last 30 days, read and unread)
        since = (datetime.now() - timedelta(days=30)).isoformat()
        cursor = conn.execute(
            """SELECT gloda_message_id, sender_email, sanitized_subject,
                      notability, body_embedding, subject_embedding
            FROM email_cache
            WHERE date >= ? AND is_read = 0 AND dismissed = 0
            ORDER BY date DESC
            LIMIT ?""",
            (since, limit),
        )
        rows = cursor.fetchall()
        results = []

        for row in rows:
            msg_id = row["gloda_message_id"]
            sender_email = row["sender_email"]

            # People score
            people_score, linked_acts, linked_scenes = self.match_people_graph(sender_email)

            # Play score (embedding similarity)
            play_score = 0.0
            email_emb = row["body_embedding"] or row["subject_embedding"]
            if email_emb:
                play_score, _, _ = self.match_play_content(email_emb)

            # Behavioral score
            behavioral_score = self._get_behavioral_score(sender_email)

            # Notability (normalized to 0-1)
            raw_notability = row["notability"] or 0
            # Gloda notability is typically 0-100
            notability_score = min(1.0, raw_notability / 100.0)

            # Weighted combination
            importance = (
                self.weights["people"] * people_score
                + self.weights["play"] * play_score
                + self.weights["behavioral"] * behavioral_score
                + self.weights["notability"] * notability_score
            )

            # Apply learned boost rules (from the attention rulebook)
            importance += self._get_rule_boost(sender_email, row["sanitized_subject"] or "")
            importance = max(0.0, min(1.0, importance))

            # Map to urgency tier
            if importance >= 0.8:
                urgency = "high"
            elif importance >= 0.5:
                urgency = "medium"
            elif importance >= 0.3:
                urgency = "low"
            else:
                urgency = "none"

            # Build reason string
            reason_parts = []
            if people_score > 0.5:
                reason_parts.append("known contact")
            if play_score > 0.4:
                reason_parts.append("matches active work")
            if behavioral_score > 0.6:
                reason_parts.append("sender you engage with")
            reason = ", ".join(reason_parts) if reason_parts else "general"

            # Update cache
            conn.execute(
                """UPDATE email_cache SET
                    importance_score = ?, people_score = ?,
                    play_score = ?, behavioral_score = ?,
                    importance_reason = ?
                WHERE gloda_message_id = ?""",
                (importance, people_score, play_score, behavioral_score, reason, msg_id),
            )

            if urgency != "none":
                results.append(
                    EmailImportanceResult(
                        gloda_message_id=msg_id,
                        importance_score=importance,
                        people_score=people_score,
                        play_score=play_score,
                        behavioral_score=behavioral_score,
                        notability_score=notability_score,
                        urgency=urgency,
                        reason=reason,
                    )
                )

        conn.commit()
        return results

    # =========================================================================
    # Matching: People graph and Play content
    # =========================================================================

    def _build_contact_email_set(self) -> set[str]:
        """Build a set of all known contact emails from Thunderbird address books.

        Cached on the service instance to avoid re-reading address books on
        every call to match_people_graph().
        """
        if hasattr(self, "_contact_emails"):
            return self._contact_emails

        emails: set[str] = set()
        try:
            contacts = self.thunderbird.list_contacts()
            for c in contacts:
                if c.email:
                    emails.add(c.email.lower())
        except Exception as e:
            logger.debug("Failed to load contacts for people graph: %s", e)

        self._contact_emails = emails
        return emails

    def match_people_graph(self, sender_email: str) -> tuple[float, list[str], list[str]]:
        """Match sender email against Thunderbird contacts and Play links.

        First checks if the sender is a known contact (address book match).
        Then checks contact_links for Play entity associations.

        Returns:
            Tuple of (people_score, linked_act_ids, linked_scene_ids).
        """
        conn = self.store._get_connection()

        # Check sender profile cache first
        profile = conn.execute(
            "SELECT people_importance, linked_act_ids, linked_scene_ids "
            "FROM email_sender_profiles WHERE sender_email = ?",
            (sender_email,),
        ).fetchone()

        if profile and profile["people_importance"] is not None:
            act_ids = json.loads(profile["linked_act_ids"]) if profile["linked_act_ids"] else []
            scene_ids = (
                json.loads(profile["linked_scene_ids"]) if profile["linked_scene_ids"] else []
            )
            return (profile["people_importance"], act_ids, scene_ids)

        score = 0.0
        act_ids: list[str] = []
        scene_ids: list[str] = []

        # Check if sender is a known contact (deduped across all address books)
        known_emails = self._build_contact_email_set()
        is_known_contact = sender_email.lower() in known_emails

        if is_known_contact:
            score = 0.5  # Base score for known contact

        # Check contact_links for Play entity associations (by email match)
        # Find contacts whose email matches the sender, then look up their links
        try:
            contacts = self.thunderbird.list_contacts(search=sender_email)
            matched_card_ids = [
                c.id for c in contacts if c.email and c.email.lower() == sender_email.lower()
            ]

            for card_id in matched_card_ids:
                links = conn.execute(
                    """SELECT DISTINCT entity_type, entity_id
                    FROM contact_links WHERE contact_id = ?""",
                    (card_id,),
                ).fetchall()
                for link in links:
                    if link["entity_type"] == "act":
                        act_ids.append(link["entity_id"])
                        score = min(1.0, score + 0.2)
                    elif link["entity_type"] == "scene":
                        scene_ids.append(link["entity_id"])
                        score = min(1.0, score + 0.1)
        except Exception as e:
            logger.debug("Failed to check contact links: %s", e)

        return (score, act_ids, scene_ids)

    def match_play_content(
        self,
        email_embedding: bytes,
        *,
        threshold: float = 0.4,
        top_k: int = 5,
    ) -> tuple[float, list[str], list[str]]:
        """Match email embedding against block_embeddings in play.db.

        Returns:
            Tuple of (play_score, matched_block_ids, matched_act_ids).
        """
        from cairn.memory.embeddings import get_embedding_service
        from cairn import play_db

        embedding_service = get_embedding_service()

        try:
            play_conn = play_db._get_connection()
            cursor = play_conn.execute("SELECT block_id, embedding FROM block_embeddings")
            candidates = [(row["block_id"], row["embedding"]) for row in cursor]
        except Exception as e:
            logger.debug("Failed to fetch play embeddings: %s", e)
            return (0.0, [], [])

        if not candidates:
            return (0.0, [], [])

        similar = embedding_service.find_similar(
            email_embedding,
            candidates,
            threshold=threshold,
            top_k=top_k,
        )

        if not similar:
            return (0.0, [], [])

        # Best similarity as the play_score
        best_score = similar[0][1]
        matched_ids = [sid for sid, _ in similar]

        # Resolve block_ids to act_ids
        act_ids: list[str] = []
        try:
            for block_id in matched_ids[:3]:
                row = play_conn.execute(
                    """SELECT b.page_id FROM blocks b
                    WHERE b.id = ?""",
                    (block_id,),
                ).fetchone()
                if row and row["page_id"]:
                    act_ids.append(row["page_id"])
        except Exception:
            pass

        return (best_score, matched_ids, list(set(act_ids)))

    # =========================================================================
    # Behavioral scoring
    # =========================================================================

    def _get_behavioral_score(self, sender_email: str) -> float:
        """Get behavioral importance score for a sender.

        Formula: 0.40×read_rate + 0.30×reply_rate + 0.20×(1-normalized_read_delay) + 0.10×star_rate
        Minimum 5 messages for reliable scoring; below that returns 0.5 (neutral).
        """
        conn = self.store._get_connection()
        profile = conn.execute(
            "SELECT behavioral_importance, total_received FROM email_sender_profiles "
            "WHERE sender_email = ?",
            (sender_email,),
        ).fetchone()

        if not profile:
            return 0.5  # Neutral for unknown senders

        if (profile["total_received"] or 0) < 5:
            return 0.5  # Not enough data

        return profile["behavioral_importance"] or 0.5

    def _get_rule_boost(self, sender_email: str, subject: str) -> float:
        """Apply learned boost rules from the attention rulebook.

        Checks sender_email and subject keyword rules. Returns the total boost
        (negative for dismiss rules, positive for priority rules).
        """
        if not hasattr(self, "_boost_rules_cache"):
            try:
                from cairn.play_db import get_active_boost_rules

                self._boost_rules_cache = get_active_boost_rules()
            except Exception:
                self._boost_rules_cache = []

        total_boost = 0.0
        sender_lower = sender_email.lower()
        subject_lower = subject.lower()

        for rule in self._boost_rules_cache:
            ft = rule["feature_type"]
            fv = rule["feature_value"].lower()
            if ft == "sender_email" and fv == sender_lower:
                total_boost += rule["boost_score"]
            elif ft == "sender_domain" and sender_lower.endswith(fv):
                total_boost += rule["boost_score"]
            elif ft == "subject_keyword" and fv in subject_lower:
                total_boost += rule["boost_score"]

        return total_boost

    def update_sender_profiles(self) -> int:
        """Aggregate read/reply/star rates per sender from email_cache.

        Returns:
            Number of profiles updated.
        """
        conn = self.store._get_connection()
        now = datetime.now().isoformat()

        # Aggregate stats per sender
        cursor = conn.execute(
            """SELECT sender_email, sender_name,
                      COUNT(*) as total,
                      SUM(is_read) as read_count,
                      SUM(is_replied) as replied_count,
                      SUM(is_starred) as starred_count
            FROM email_cache
            GROUP BY sender_email"""
        )

        updated = 0
        for row in cursor:
            total = row["total"]
            if total == 0:
                continue

            read_rate = (row["read_count"] or 0) / total
            reply_rate = (row["replied_count"] or 0) / total
            star_rate = (row["starred_count"] or 0) / total

            # Compute average read delay for this sender
            delay_cursor = conn.execute(
                """SELECT AVG(
                    CAST((julianday(read_state_changed_at) - julianday(date)) * 86400 AS REAL)
                ) as avg_delay
                FROM email_cache
                WHERE sender_email = ? AND read_state_changed_at IS NOT NULL""",
                (row["sender_email"],),
            )
            delay_row = delay_cursor.fetchone()
            avg_delay = delay_row["avg_delay"] if delay_row else None

            # Normalize read delay (faster = higher score)
            # Assume 7 days as the max "slow" threshold
            delay_score = 0.5
            if avg_delay is not None and avg_delay >= 0:
                delay_score = max(0.0, 1.0 - (avg_delay / (7 * 86400)))

            # Behavioral formula
            behavioral = (
                0.40 * read_rate + 0.30 * reply_rate + 0.20 * delay_score + 0.10 * star_rate
            )

            conn.execute(
                """INSERT INTO email_sender_profiles (
                    sender_email, sender_name, total_received, total_read,
                    total_replied, total_starred, avg_read_delay_seconds,
                    read_rate, reply_rate, star_rate,
                    behavioral_importance, first_seen_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(sender_email) DO UPDATE SET
                    sender_name = excluded.sender_name,
                    total_received = excluded.total_received,
                    total_read = excluded.total_read,
                    total_replied = excluded.total_replied,
                    total_starred = excluded.total_starred,
                    avg_read_delay_seconds = excluded.avg_read_delay_seconds,
                    read_rate = excluded.read_rate,
                    reply_rate = excluded.reply_rate,
                    star_rate = excluded.star_rate,
                    behavioral_importance = excluded.behavioral_importance,
                    updated_at = excluded.updated_at""",
                (
                    row["sender_email"],
                    row["sender_name"],
                    total,
                    row["read_count"] or 0,
                    row["replied_count"] or 0,
                    row["starred_count"] or 0,
                    avg_delay,
                    read_rate,
                    reply_rate,
                    star_rate,
                    behavioral,
                    now,
                    now,
                ),
            )
            updated += 1

        conn.commit()
        return updated

    # =========================================================================
    # Surfacing: Get important unread emails
    # =========================================================================

    def get_important_unread(
        self,
        *,
        min_importance: float = 0.3,
        limit: int = 10,
    ) -> list[dict]:
        """Get scored unread emails for surfacing.

        Returns TRUSTED ZONE data only — no body text, no unsanitized subjects.
        """
        conn = self.store._get_connection()

        now = datetime.now().isoformat()
        cursor = conn.execute(
            """SELECT gloda_message_id, folder_name, account_email,
                      sanitized_subject,
                      sender_name, sender_email, date,
                      importance_score, people_score, play_score,
                      behavioral_score, importance_reason
            FROM email_cache
            WHERE is_read = 0
              AND dismissed = 0
              AND (snoozed_until IS NULL OR snoozed_until < ?)
              AND importance_score >= ?
            ORDER BY importance_score DESC
            LIMIT ?""",
            (now, min_importance, limit),
        )

        results = []
        for row in cursor:
            # Map importance to urgency
            score = row["importance_score"] or 0
            if score >= 0.8:
                urgency = "high"
            elif score >= 0.5:
                urgency = "medium"
            else:
                urgency = "low"

            results.append(
                {
                    "gloda_message_id": row["gloda_message_id"],
                    "folder_name": row["folder_name"],
                    "account_email": row["account_email"] or "",
                    "subject": row["sanitized_subject"],
                    "sender_name": row["sender_name"],
                    "sender_email": row["sender_email"],
                    "date": row["date"],
                    "importance_score": score,
                    "urgency": urgency,
                    "reason": row["importance_reason"],
                }
            )

        return results

    def get_recent_emails(self, *, days: int = 30) -> list[dict]:
        """Get all emails from the last N days, sorted by score then recency.

        Returns TRUSTED ZONE data only — no body text, no unsanitized subjects.
        Includes both read and unread emails. Excludes dismissed.
        """
        conn = self.store._get_connection()
        since = (datetime.now() - timedelta(days=days)).isoformat()

        cursor = conn.execute(
            """SELECT gloda_message_id, folder_name, account_email,
                      sanitized_subject,
                      sender_name, sender_email, date, is_read,
                      importance_score, people_score, play_score,
                      behavioral_score, importance_reason
            FROM email_cache
            WHERE date >= ?
              AND dismissed = 0
            ORDER BY COALESCE(importance_score, 0.0) DESC, date DESC""",
            (since,),
        )

        results = []
        for row in cursor:
            score = row["importance_score"] or 0
            if score >= 0.8:
                urgency = "high"
            elif score >= 0.5:
                urgency = "medium"
            elif score >= 0.3:
                urgency = "low"
            else:
                urgency = "none"

            results.append(
                {
                    "gloda_message_id": row["gloda_message_id"],
                    "folder_name": row["folder_name"],
                    "account_email": row["account_email"] or "",
                    "subject": row["sanitized_subject"],
                    "sender_name": row["sender_name"],
                    "sender_email": row["sender_email"],
                    "date": row["date"],
                    "is_read": bool(row["is_read"]),
                    "importance_score": score,
                    "urgency": urgency,
                    "reason": row["importance_reason"],
                }
            )

        return results

    # =========================================================================
    # Full refresh pipeline
    # =========================================================================

    def full_refresh(self) -> dict[str, int]:
        """Run full pipeline: sync → embed → update profiles → score.

        Returns:
            Dict with counts for each step.
        """
        counts: dict[str, int] = {}

        try:
            counts["synced"] = self.sync_emails()
        except Exception as e:
            logger.error("Email sync failed: %s", e)
            counts["synced"] = 0

        try:
            counts["profiles_updated"] = self.update_sender_profiles()
        except Exception as e:
            logger.error("Sender profile update failed: %s", e)
            counts["profiles_updated"] = 0

        try:
            counts["embedded"] = self.embed_emails()
        except Exception as e:
            logger.error("Email embedding failed: %s", e)
            counts["embedded"] = 0

        try:
            results = self.score_importance()
            counts["scored"] = len(results)
        except Exception as e:
            logger.error("Email scoring failed: %s", e)
            counts["scored"] = 0

        logger.info(
            "Email refresh complete: synced=%d, profiles=%d, embedded=%d, scored=%d",
            counts.get("synced", 0),
            counts.get("profiles_updated", 0),
            counts.get("embedded", 0),
            counts.get("scored", 0),
        )

        return counts

    # =========================================================================
    # Sync state helpers
    # =========================================================================

    def _load_mbox_offsets(self) -> dict[str, int]:
        """Load all mbox byte offsets from email_sync_state.

        Keys follow the pattern "mbox_offset:{absolute_path}". Values are
        the file byte position at which the next incremental scan should start.
        """
        conn = self.store._get_connection()
        rows = conn.execute(
            "SELECT key, value FROM email_sync_state WHERE key LIKE 'mbox_offset:%'"
        ).fetchall()
        return {row["key"]: int(row["value"]) for row in rows}

    def _flush_mbox_offsets(self, offsets: dict[str, int]) -> None:
        """Persist mbox byte offsets back to email_sync_state.

        Uses INSERT ... ON CONFLICT(key) DO UPDATE so the operation is
        idempotent and safe to call after any sync, even partial ones.
        """
        conn = self.store._get_connection()
        now = datetime.now().isoformat()
        for key, value in offsets.items():
            conn.execute(
                """INSERT INTO email_sync_state (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at""",
                (key, str(value), now),
            )
        conn.commit()

    def _get_last_sync_time(self) -> datetime | None:
        """Get the last sync timestamp."""
        conn = self.store._get_connection()
        row = conn.execute("SELECT value FROM email_sync_state WHERE key = 'last_sync'").fetchone()
        if row:
            try:
                return datetime.fromisoformat(row["value"])
            except (ValueError, TypeError):
                pass
        return None

    def _set_sync_state(self, key: str, value: str) -> None:
        """Set a sync state value."""
        conn = self.store._get_connection()
        conn.execute(
            """INSERT INTO email_sync_state (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at""",
            (key, value, datetime.now().isoformat()),
        )
        conn.commit()


# =============================================================================
# Background Sync Loop
# =============================================================================


class EmailSyncLoop:
    """Background thread that periodically refreshes email intelligence."""

    def __init__(
        self,
        service: EmailIntelligenceService,
        interval_seconds: int = 300,
    ):
        self.service = service
        self.interval = interval_seconds
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the background sync loop as a daemon thread."""
        if self._thread is not None and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="email-sync-loop",
            daemon=True,
        )
        self._thread.start()
        logger.info("Email sync loop started (interval=%ds)", self.interval)

    def stop(self) -> None:
        """Signal the sync loop to stop gracefully."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=10)
            self._thread = None
        logger.info("Email sync loop stopped")

    def _run(self) -> None:
        """Main loop — runs full_refresh at intervals."""
        while not self._stop_event.is_set():
            try:
                self.service.full_refresh()
            except Exception as e:
                logger.error("Email sync loop error: %s", e)

            # Wait for the interval or until stopped
            self._stop_event.wait(self.interval)
