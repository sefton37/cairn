"""Thunderbird and attention RPC handlers.

These handlers manage Thunderbird calendar/contact integration
and CAIRN attention surfacing.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from cairn.db import Database

from . import RpcError
from .play import get_current_play_path


logger = logging.getLogger(__name__)


# =============================================================================
# Thunderbird Integration Handlers
# =============================================================================


def handle_cairn_thunderbird_status(_db: Database) -> dict[str, Any]:
    """Check if Thunderbird integration is available."""
    from cairn.cairn.thunderbird import ThunderbirdBridge

    bridge = ThunderbirdBridge.auto_detect()
    if bridge is None:
        return {
            "available": False,
            "message": "Thunderbird profile not detected. Install Thunderbird and create a profile to enable calendar and contact integration.",
        }

    status = bridge.get_status()
    return {
        "available": True,
        "profile_path": str(bridge.config.profile_path),
        "has_contacts": status.get("contacts_available", False),
        "has_calendar": status.get("calendar_available", False),
        "contact_count": status.get("contact_count", 0),
    }


def handle_thunderbird_check(db: Database) -> dict[str, Any]:
    """Check Thunderbird installation and discover profiles."""
    from cairn.cairn.thunderbird import (
        get_thunderbird_integration_state,
        ThunderbirdProfile,
        ThunderbirdAccount,
    )
    from cairn.cairn.store import get_cairn_store

    # Get integration state from Thunderbird
    integration = get_thunderbird_integration_state()

    # Get stored preferences
    play_path = get_current_play_path(db)
    if play_path:
        store = get_cairn_store()
        stored_state = store.get_integration_state("thunderbird")
    else:
        stored_state = None

    # Determine integration state
    if stored_state and stored_state["state"] == "declined":
        state = "declined"
    elif stored_state and stored_state["state"] == "active":
        state = "active"
    else:
        state = "not_configured"

    # Serialize profiles
    def serialize_account(acc: ThunderbirdAccount) -> dict:
        return {
            "id": acc.id,
            "name": acc.name,
            "email": acc.email,
            "type": acc.type,
            "server": acc.server,
            "calendars": acc.calendars,
            "address_books": acc.address_books,
        }

    def serialize_profile(prof: ThunderbirdProfile) -> dict:
        return {
            "name": prof.name,
            "path": str(prof.path),
            "is_default": prof.is_default,
            "accounts": [serialize_account(a) for a in prof.accounts],
        }

    return {
        "installed": integration.installed,
        "install_suggestion": integration.install_suggestion,
        "profiles": [serialize_profile(p) for p in integration.profiles],
        "integration_state": state,
        "active_profiles": stored_state["config"].get("active_profiles", []) if stored_state and stored_state["config"] else [],
    }


def handle_thunderbird_configure(
    db: Database,
    *,
    active_profiles: list[str],
    active_accounts: list[str] | None = None,
    all_active: bool = False,
) -> dict[str, Any]:
    """Configure Thunderbird integration."""
    from cairn.cairn.store import get_cairn_store

    play_path = get_current_play_path(db)
    if not play_path:
        raise RpcError(code=-32000, message="No Play path configured")

    store = get_cairn_store()

    config = {
        "active_profiles": active_profiles,
        "active_accounts": active_accounts or [],
        "all_active": all_active,
    }

    store.set_integration_active("thunderbird", config)

    return {"success": True, "config": config}


def handle_thunderbird_decline(db: Database) -> dict[str, Any]:
    """Mark Thunderbird integration as declined (never ask again)."""
    from cairn.cairn.store import get_cairn_store

    play_path = get_current_play_path(db)
    if not play_path:
        raise RpcError(code=-32000, message="No Play path configured")

    store = get_cairn_store()
    store.set_integration_declined("thunderbird")

    return {"success": True}


def handle_thunderbird_reset(db: Database) -> dict[str, Any]:
    """Reset Thunderbird integration (re-enable prompts)."""
    from cairn.cairn.store import get_cairn_store

    play_path = get_current_play_path(db)
    if not play_path:
        raise RpcError(code=-32000, message="No Play path configured")

    store = get_cairn_store()
    store.clear_integration_decline("thunderbird")

    return {"success": True}


# =============================================================================
# CAIRN Attention Handler
# =============================================================================


def handle_cairn_attention(
    db: Database,
    *,
    hours: int = 168,  # 7 days
    limit: int = 10,
) -> dict[str, Any]:
    """Get items that need attention - primarily upcoming calendar events.

    Shows the next 7 days by default for the 'What Needs My Attention' section.
    """
    from cairn.cairn.store import get_cairn_store
    from cairn.cairn.surfacing import CairnSurfacer
    from cairn.cairn.thunderbird import ThunderbirdBridge
    from cairn import play_fs
    from cairn.settings import settings

    play_path = get_current_play_path(db)
    if not play_path:
        return {"count": 0, "items": []}

    # Set up CAIRN components
    cairn_db_path = settings.data_dir / "talkingrock.db"
    store = get_cairn_store()

    # Get Thunderbird bridge if configured
    thunderbird = None
    email_service = None
    tb_state = store.get_integration_state("thunderbird")
    if tb_state and tb_state["state"] == "active":
        thunderbird = ThunderbirdBridge.auto_detect()

        # Set up email intelligence if Gloda database is available
        if thunderbird and thunderbird.has_email_db():
            try:
                from cairn.services.email_intelligence import EmailIntelligenceService
                email_service = EmailIntelligenceService(
                    cairn_store=store, thunderbird=thunderbird,
                )
            except Exception as e:
                logger.debug("Email intelligence unavailable: %s", e)

    # Create surfacer and get attention items
    surfacer = CairnSurfacer(
        cairn_store=store,
        thunderbird=thunderbird,
        email_service=email_service,
    )

    items = surfacer.surface_attention(hours=hours, limit=max(limit, 200))

    # Build act_id -> title/color lookup from play_fs
    acts, _ = play_fs.list_acts()
    act_info = {a.act_id: {"title": a.title, "color": a.color} for a in acts}

    # Run critical health checks at startup (data integrity only)
    health_warnings: list[dict] = []
    try:
        from cairn.cairn.health.checks.data_integrity import DataIntegrityCheck
        from cairn.cairn.health.runner import Severity
        integrity_check = DataIntegrityCheck(cairn_db_path)
        integrity_results = integrity_check.run()
        for result in integrity_results:
            if result.severity == Severity.CRITICAL:
                health_warnings.append({
                    "check": result.check_name,
                    "severity": result.severity.value,
                    "title": result.title,
                    "details": result.details,
                })
    except Exception as e:
        logger.debug("Health check at startup failed: %s", e)

    # Load user priorities to include in response
    from cairn.play_db import get_attention_priorities

    try:
        priorities = get_attention_priorities()
    except Exception:
        priorities = {}

    return {
        "count": len(items),
        "items": [
            {
                "entity_type": item.entity_type,
                "entity_id": item.entity_id,
                "title": item.title,
                "reason": item.reason,
                "urgency": item.urgency,
                "calendar_start": item.calendar_start.isoformat() if item.calendar_start else None,
                "calendar_end": item.calendar_end.isoformat() if item.calendar_end else None,
                "is_recurring": item.is_recurring,
                "recurrence_frequency": item.recurrence_frequency,
                "next_occurrence": item.next_occurrence.isoformat() if item.next_occurrence else None,
                "act_id": item.act_id,
                "scene_id": item.scene_id,
                "act_title": act_info.get(item.act_id, {}).get("title") if item.act_id else None,
                "act_color": act_info.get(item.act_id, {}).get("color") if item.act_id else None,
                "user_priority": priorities.get(item.entity_id),
                "learned_boost": item.learned_boost,
                "boost_reasons": item.boost_reasons,
                # Email-specific fields
                "sender_name": item.sender_name,
                "sender_email": item.sender_email,
                "account_email": item.account_email,
                "email_date": item.email_date.isoformat() if item.email_date else None,
                "importance_score": item.importance_score,
                "importance_reason": item.importance_reason,
                "email_message_id": item.email_message_id,
                "is_read": item.is_read,
            }
            for item in items
        ],
        "health_warnings": health_warnings,
    }


def handle_cairn_attention_reorder(
    db: Database,
    *,
    ordered_scene_ids: list[str] | None = None,
    ordered_entities: list[list[str]] | None = None,
) -> dict[str, Any]:
    """Reorder attention items based on user drag-and-drop.

    Persists the new order, records history for priority learning,
    then asks CAIRN to analyze the reorder and propose memories
    for user approval via conversation.
    """
    from cairn.cairn.models import ActivityType
    from cairn.services.priority_signal_service import PrioritySignalService
    from cairn.services.priority_analysis_service import PriorityAnalysisService
    from cairn.services.conversation_service import ConversationService
    from cairn import play_db

    play_path = get_current_play_path(db)

    # Normalize ordered_entities from JSON (list of [type, id] arrays) to tuples
    entity_tuples: list[tuple[str, str]] | None = None
    if ordered_entities:
        entity_tuples = [(e[0], e[1]) for e in ordered_entities]

    # Derive ordered_scene_ids from entities for backward compat
    if entity_tuples and not ordered_scene_ids:
        ordered_scene_ids = [eid for etype, eid in entity_tuples if etype == "scene"]

    # 1. Capture old order BEFORE persisting
    try:
        old_priorities = play_db.get_attention_priorities()
    except Exception:
        old_priorities = {}

    # 2. Gather scene details for context
    scene_details: list[dict[str, Any]] = []
    if ordered_scene_ids:
        try:
            conn = play_db._get_connection()
            placeholders = ",".join("?" * len(ordered_scene_ids))
            cursor = conn.execute(
                f"""SELECT s.scene_id, s.title, s.stage,
                           substr(s.notes, 1, 300) as notes,
                           s.calendar_event_start AS start_date,
                           s.calendar_event_end   AS end_date,
                           s.act_id,
                           a.title as act_title
                    FROM scenes s
                    LEFT JOIN acts a ON s.act_id = a.act_id
                    WHERE s.scene_id IN ({placeholders})""",
                ordered_scene_ids,
            )
            scene_details = [dict(row) for row in cursor.fetchall()]
        except Exception:
            logger.warning("Failed to look up scene details for reorder", exc_info=True)

    # 3. Persist new order and record history (DB only)
    service = PrioritySignalService()
    result = service.process_reorder(
        ordered_scene_ids=ordered_scene_ids,
        ordered_entities=entity_tuples,
    )

    # 4. Get active conversation (or create one)
    conversation_id: str | None = None
    try:
        conv_service = ConversationService()
        active_conv = conv_service.get_active()
        if active_conv:
            conversation_id = active_conv.id
        else:
            new_conv = conv_service.start()
            conversation_id = new_conv.id
    except Exception:
        logger.debug("Failed to get/create conversation for analysis", exc_info=True)

    # 5. Call CAIRN analysis (failure → empty analysis, never a 500)
    analysis_text = ""
    if conversation_id and ordered_scene_ids:
        try:
            # Add urgency info from old surfaced items to scene_details
            for detail in scene_details:
                sid = detail.get("scene_id", "")
                if sid in old_priorities:
                    detail["urgency"] = f"priority #{old_priorities[sid] + 1}"
                else:
                    detail["urgency"] = "unranked"

            analyzer = PriorityAnalysisService()
            analysis_text = analyzer.analyze_reorder(
                db=db,
                ordered_scene_ids=ordered_scene_ids,
                old_priorities=old_priorities,
                scene_details=scene_details,
                conversation_id=conversation_id,
            )
        except Exception:
            logger.warning("CAIRN priority analysis failed", exc_info=True)

    # 6. Log activity
    if play_path:
        try:
            from cairn.cairn.store import get_cairn_store as _get_cairn_store
            store = _get_cairn_store()
            if ordered_scene_ids:
                store.log_activity(
                    entity_type="scene",
                    entity_id=ordered_scene_ids[0],
                    activity_type=ActivityType.PRIORITY_SET,
                )
        except Exception:
            logger.debug("Failed to log priority activity", exc_info=True)

    # 7. Extract/update boost rules from accumulated reorder history
    try:
        from cairn.services.priority_learning_service import PriorityLearningService

        learner = PriorityLearningService()
        learner.extract_rules()
    except Exception:
        logger.debug("Rule extraction failed", exc_info=True)

    return {
        "priorities_updated": result["priorities_updated"],
        "analysis_text": analysis_text,
        "conversation_id": conversation_id,
    }


# =============================================================================
# Debug Log Handler
# =============================================================================


def handle_debug_log(_db: Database, *, msg: str) -> dict[str, Any]:
    """Log a debug message from the frontend to stderr."""
    import sys
    print(f"[JS] {msg}", file=sys.stderr, flush=True)
    return {"ok": True}


# =============================================================================
# Email Intelligence Handlers
# =============================================================================


def handle_cairn_email_open(db: Database, *, message_id: int) -> dict[str, Any]:
    """Open a specific email in Thunderbird using the RFC Message-ID (mid: URI)."""
    import subprocess

    from cairn.cairn.store import get_cairn_store

    store = get_cairn_store()
    conn = store._get_connection()

    row = conn.execute(
        "SELECT gloda_message_id, header_message_id FROM email_cache WHERE gloda_message_id = ?",
        (message_id,),
    ).fetchone()

    if not row:
        raise RpcError(code=-32001, message="Email not found in cache")

    # Mark as surfaced
    conn.execute(
        "UPDATE email_cache SET surfaced = 1, surfaced_at = ? WHERE gloda_message_id = ?",
        (datetime.now().isoformat(), message_id),
    )
    conn.commit()

    # Open specific message in Thunderbird via mid: URI
    header_mid = row["header_message_id"]
    try:
        if header_mid:
            subprocess.Popen(
                ["thunderbird", f"mid:{header_mid}"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            # Fallback: just open Thunderbird mail tab
            subprocess.Popen(
                ["thunderbird", "-mail"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
    except FileNotFoundError:
        logger.warning("Thunderbird not found in PATH")

    return {"success": True, "message_id": message_id}


def handle_cairn_email_dismiss(db: Database, *, message_id: int) -> dict[str, Any]:
    """Dismiss an email from the attention pane."""
    from cairn.cairn.store import get_cairn_store

    store = get_cairn_store()
    conn = store._get_connection()

    row = conn.execute(
        "SELECT gloda_message_id FROM email_cache WHERE gloda_message_id = ?",
        (message_id,),
    ).fetchone()

    if not row:
        raise RpcError(code=-32001, message="Email not found in cache")

    conn.execute(
        "UPDATE email_cache SET dismissed = 1 WHERE gloda_message_id = ?",
        (message_id,),
    )
    conn.commit()

    return {"success": True, "message_id": message_id}


def handle_cairn_email_snooze(
    db: Database, *, message_id: int, hours: int = 4
) -> dict[str, Any]:
    """Snooze an email — hide it from the attention pane for N hours."""
    from datetime import timedelta

    from cairn.cairn.store import get_cairn_store

    store = get_cairn_store()
    conn = store._get_connection()

    row = conn.execute(
        "SELECT gloda_message_id FROM email_cache WHERE gloda_message_id = ?",
        (message_id,),
    ).fetchone()

    if not row:
        raise RpcError(code=-32001, message="Email not found in cache")

    snooze_until = (datetime.now() + timedelta(hours=hours)).isoformat()
    conn.execute(
        "UPDATE email_cache SET snoozed_until = ? WHERE gloda_message_id = ?",
        (snooze_until, message_id),
    )
    conn.commit()

    return {"success": True, "message_id": message_id, "snoozed_until": snooze_until}


def handle_cairn_email_upvote(
    db: Database, *, message_id: int
) -> dict[str, Any]:
    """Increase an email's importance score and learn a boost rule for its sender."""
    from cairn.cairn.store import get_cairn_store

    store = get_cairn_store()
    conn = store._get_connection()

    row = conn.execute(
        "SELECT gloda_message_id, sender_email, importance_score FROM email_cache WHERE gloda_message_id = ?",
        (message_id,),
    ).fetchone()

    if not row:
        raise RpcError(code=-32001, message="Email not found in cache")

    current_score = row["importance_score"] or 0.0
    new_score = min(1.0, current_score + 0.15)

    conn.execute(
        "UPDATE email_cache SET importance_score = ? WHERE gloda_message_id = ?",
        (new_score, message_id),
    )
    conn.commit()

    # Learn a boost rule for this sender
    sender_email = row["sender_email"]
    if sender_email:
        try:
            from cairn.play_db import upsert_boost_rule
            now = datetime.now().isoformat()
            upsert_boost_rule({
                "id": f"email-sender-{sender_email}",
                "feature_type": "sender_email",
                "feature_value": sender_email,
                "boost_score": 0.15,
                "confidence": 1.0,
                "sample_count": 1,
                "description": f"Upvoted email from {sender_email}",
                "active": 1,
                "created_at": now,
                "updated_at": now,
            })
        except Exception as e:
            logger.warning("Failed to create boost rule: %s", e)

    return {"success": True, "message_id": message_id, "new_score": new_score}


def handle_cairn_email_downvote(
    db: Database, *, message_id: int
) -> dict[str, Any]:
    """Decrease an email's importance score and learn a negative boost rule for its sender."""
    from cairn.cairn.store import get_cairn_store

    store = get_cairn_store()
    conn = store._get_connection()

    row = conn.execute(
        "SELECT gloda_message_id, sender_email, importance_score FROM email_cache WHERE gloda_message_id = ?",
        (message_id,),
    ).fetchone()

    if not row:
        raise RpcError(code=-32001, message="Email not found in cache")

    current_score = row["importance_score"] or 0.0
    new_score = max(0.0, current_score - 0.15)

    conn.execute(
        "UPDATE email_cache SET importance_score = ? WHERE gloda_message_id = ?",
        (new_score, message_id),
    )
    conn.commit()

    # Learn a negative boost rule for this sender
    sender_email = row["sender_email"]
    if sender_email:
        try:
            from cairn.play_db import upsert_boost_rule
            now = datetime.now().isoformat()
            upsert_boost_rule({
                "id": f"email-sender-{sender_email}",
                "feature_type": "sender_email",
                "feature_value": sender_email,
                "boost_score": -0.15,
                "confidence": 1.0,
                "sample_count": 1,
                "description": f"Downvoted email from {sender_email}",
                "active": 1,
                "created_at": now,
                "updated_at": now,
            })
        except Exception as e:
            logger.warning("Failed to create boost rule: %s", e)

    return {"success": True, "message_id": message_id, "new_score": new_score}
