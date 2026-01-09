"""Core handlers.

Handles protocol initialization and basic connectivity.
"""

from __future__ import annotations

from typing import Any

from reos.rpc.router import register


@register("initialize")
def handle_initialize() -> dict[str, Any]:
    """Initialize the RPC connection and return protocol info."""
    return {
        "protocolVersion": "jsonrpc-2.0",
        "serverInfo": {"name": "reos-ui-kernel", "version": "0.1.0"},
    }


@register("ping")
def handle_ping() -> dict[str, Any]:
    """Simple health check."""
    return {"ok": True}
