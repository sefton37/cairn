from __future__ import annotations

from pathlib import Path

from cairn.db import get_db


def test_mcp_notifications_are_ignored(configured_repo: Path) -> None:
    import cairn.mcp_server as mcp

    db = get_db()
    # Notification: no id
    resp = mcp._handle_jsonrpc_request(
        db,
        {
            "jsonrpc": "2.0",
            "method": "tools/list",
        },
    )
    assert resp is None
