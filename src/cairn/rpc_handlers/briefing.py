"""State briefing RPC handlers.

Exposes the StateBriefingService over RPC for frontend consumption.
Two endpoints: get the current cached briefing, or generate a fresh one.
"""

from __future__ import annotations

from typing import Any

from cairn.db import Database
from cairn.services.state_briefing_service import StateBriefingService

from ._base import require_params, rpc_handler

# Singleton service instance
_service: StateBriefingService | None = None


def _get_service() -> StateBriefingService:
    global _service
    if _service is None:
        _service = StateBriefingService()
    return _service


@rpc_handler("lifecycle/briefing/get")
def handle_briefing_get(db: Database) -> dict[str, Any]:
    """Get the current state briefing (if not stale).

    Returns the most recently generated briefing if it was created within the
    last 24 hours. Returns None if no briefing exists or it has gone stale.
    """
    service = _get_service()
    briefing = service.get_current()
    return {"briefing": briefing.to_dict() if briefing else None}


@require_params()
@rpc_handler("lifecycle/briefing/generate")
def handle_briefing_generate(db: Database, *, trigger: str = "manual") -> dict[str, Any]:
    """Generate a fresh state briefing.

    Forces regeneration regardless of cache freshness. The new briefing is
    persisted and returned.

    Args:
        trigger: Source of the request ('app_start', 'new_conversation', 'manual').
    """
    service = _get_service()
    briefing = service.generate(trigger=trigger)
    return {"briefing": briefing.to_dict()}
