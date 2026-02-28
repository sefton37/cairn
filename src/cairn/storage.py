from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime

from pathlib import Path

from .db import Database, get_db
from .models import Event
from .settings import settings

logger = logging.getLogger(__name__)


def get_default_repo_path() -> Path | None:
    """Return the configured repo root path from the database, or None.

    Used by storage trigger tests (and previously by alignment module) to
    locate the active git repository. Returns None if no path is configured.
    """
    db = get_db()
    value = db.get_state(key="repo_path")
    return Path(value) if value else None


def _utcnow() -> datetime:
    return datetime.now(UTC)


def append_event(event: Event) -> str:
    """Store an event to SQLite; fallback to JSONL for debugging."""
    db = get_db()
    event_id = str(uuid.uuid4())

    # Try SQLite first
    try:
        db.insert_event(
            event_id=event_id,
            source=event.source,
            kind=event.payload_metadata.get("kind") if event.payload_metadata else None,
            ts=event.ts.isoformat(),
            payload_metadata=json.dumps(event.payload_metadata) if event.payload_metadata else None,
            note=event.note,
        )
        return event_id
    except Exception as exc:
        # Fallback to JSONL for debugging/recovery
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        record = {
            "id": event_id,
            "source": event.source,
            "ts": event.ts.isoformat(),
            "payload_metadata": event.payload_metadata,
            "note": event.note,
            "error": f"SQLite failed, fell back to JSONL: {str(exc)}",
        }
        with settings.events_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=True) + "\n")
        return event_id


def _maybe_emit_review_trigger(
    *,
    db: Database,
    recent_event_payload: dict[str, object] | None,
) -> None:
    """Insert a review-trigger event if context budget is nearing capacity.

    Disabled — alignment module was extracted with ReOS.
    """
    return


def iter_events(limit: int | None = None) -> Iterable[tuple[str, Event]]:
    """Yield events from SQLite storage (newest first)."""
    db = get_db()
    rows = db.iter_events_recent(limit=limit or 1000)

    for row in rows:
        try:
            payload = None
            payload_metadata = row["payload_metadata"]
            if payload_metadata:
                payload = json.loads(str(payload_metadata))

            ts_str = row["ts"]
            # Parse the ISO format timestamp back to datetime
            from datetime import datetime

            ts = datetime.fromisoformat(str(ts_str).replace("Z", "+00:00"))

            evt = Event(
                source=str(row["source"]),
                ts=ts,
                payload_metadata=payload,
                note=str(row["note"]) if row["note"] else None,
            )
            event_id = str(row["id"])
            yield event_id, evt
        except (json.JSONDecodeError, TypeError, ValueError) as e:
            logger.warning(
                "Skipping malformed event (id=%s): %s",
                row.get("id", "unknown"),
                e,
            )
            continue
