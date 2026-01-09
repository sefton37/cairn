"""CAIRN handlers.

Manages CAIRN (Attention Minder) and Thunderbird integration.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from reos.db import Database
from reos.rpc.router import register
from reos.rpc.types import RpcError


def get_current_play_path(db: Database) -> str | None:
    """Get the current play path from the database."""
    from reos.play_fs import list_acts

    acts, active_id = list_acts()
    if active_id:
        for act in acts:
            if act.act_id == active_id and act.repo_path:
                return act.repo_path
    return None


@register("cairn/thunderbird/status", needs_db=True)
def handle_thunderbird_status(_db: Database) -> dict[str, Any]:
    """Check if Thunderbird integration is available."""
    from reos.cairn.thunderbird import ThunderbirdBridge

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


@register("thunderbird/check", needs_db=True)
def handle_thunderbird_check(db: Database) -> dict[str, Any]:
    """Check Thunderbird installation and discover profiles."""
    from reos.cairn.thunderbird import (
        get_thunderbird_integration_state,
        ThunderbirdProfile,
        ThunderbirdAccount,
    )
    from reos.cairn.store import CairnStore

    # Get integration state from Thunderbird
    integration = get_thunderbird_integration_state()

    # Get stored preferences
    play_path = get_current_play_path(db)
    if play_path:
        store = CairnStore(Path(play_path) / ".cairn" / "cairn.db")
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


@register("thunderbird/configure", needs_db=True)
def handle_thunderbird_configure(
    db: Database,
    *,
    active_profiles: list[str],
    active_accounts: list[str] | None = None,
    all_active: bool = False,
) -> dict[str, Any]:
    """Configure Thunderbird integration."""
    from reos.cairn.store import CairnStore

    play_path = get_current_play_path(db)
    if not play_path:
        raise RpcError(code=-32000, message="No Play path configured")

    store = CairnStore(Path(play_path) / ".cairn" / "cairn.db")

    config = {
        "active_profiles": active_profiles,
        "active_accounts": active_accounts or [],
        "all_active": all_active,
    }

    store.set_integration_active("thunderbird", config)

    return {"success": True, "config": config}


@register("thunderbird/decline", needs_db=True)
def handle_thunderbird_decline(db: Database) -> dict[str, Any]:
    """Mark Thunderbird integration as declined (never ask again)."""
    from reos.cairn.store import CairnStore

    play_path = get_current_play_path(db)
    if not play_path:
        raise RpcError(code=-32000, message="No Play path configured")

    store = CairnStore(Path(play_path) / ".cairn" / "cairn.db")
    store.set_integration_declined("thunderbird")

    return {"success": True}


@register("thunderbird/reset", needs_db=True)
def handle_thunderbird_reset(db: Database) -> dict[str, Any]:
    """Reset Thunderbird integration (re-enable prompts)."""
    from reos.cairn.store import CairnStore

    play_path = get_current_play_path(db)
    if not play_path:
        raise RpcError(code=-32000, message="No Play path configured")

    store = CairnStore(Path(play_path) / ".cairn" / "cairn.db")
    store.clear_integration_decline("thunderbird")

    return {"success": True}
