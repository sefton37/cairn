"""HTTP authentication handler for the PWA.

Thin wrapper around auth.create_session_from_pam() with rate limiting
and audit logging. This module is only used by the HTTP RPC layer
(http_rpc.py) — the Tauri desktop app uses the Polkit path instead.
"""

from __future__ import annotations

import logging
from typing import Any

from reos import auth
from reos.security import (
    AuditEventType,
    RateLimitExceeded,
    audit_log,
    check_rate_limit,
)

logger = logging.getLogger(__name__)


def http_login(*, username: str, credential: str) -> dict[str, Any]:
    """Authenticate via PAM and return a session token.

    Rate-limited to 5 attempts per 60 seconds (configured in security.py).
    All attempts are audit-logged regardless of outcome.
    """
    try:
        check_rate_limit("auth")
    except RateLimitExceeded as e:
        audit_log(
            AuditEventType.RATE_LIMIT_EXCEEDED,
            {"category": "auth", "username": username},
        )
        logger.warning("Auth rate limit exceeded for %s", username)
        return {"success": False, "error": str(e)}

    result = auth.create_session_from_pam(username, credential)

    if result.get("success"):
        audit_log(
            AuditEventType.AUTH_LOGIN_SUCCESS,
            {"username": username, "source": "pwa"},
        )
    else:
        audit_log(
            AuditEventType.AUTH_LOGIN_FAILED,
            {"username": username, "source": "pwa"},
        )

    return result


def http_logout(*, session_token: str) -> dict[str, Any]:
    """Invalidate a session."""
    result = auth.logout(session_token)
    if result.get("success"):
        audit_log(AuditEventType.AUTH_LOGOUT, {"source": "pwa"})
    return result
