from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from reos.models import Event
from reos.storage import append_event


def _count_kind(db_rows: list[dict[str, object]], kind: str) -> int:
    return sum(1 for r in db_rows if r.get("kind") == kind)


def test_append_event_does_not_emit_triggers_for_single_file_change(
    temp_git_repo: Path,
    isolated_db_singleton: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = temp_git_repo

    # Create a big change in a single file.
    big = repo / "src" / "reos" / "example.py"
    big.write_text(big.read_text(encoding="utf-8") + ("\n".join(["x = 1"] * 200) + "\n"), encoding="utf-8")

    # Ensure storage looks at our temp repo.
    import reos.storage as storage_mod

    monkeypatch.setattr(storage_mod, "get_default_repo_path", lambda: repo)

    # Append an event; should not emit any triggers for this scenario.
    append_event(Event(source="test", ts=datetime.now(UTC), payload_metadata={"kind": "smoke"}))

    from reos.db import get_db

    db = get_db()
    rows = db.iter_events_recent(limit=50)

    assert _count_kind(rows, "review_trigger") == 0
    assert _count_kind(rows, "alignment_trigger") == 0
