"""HTTP authentication handler for the PWA.

Thin wrapper around auth.create_session_from_pam() with rate limiting
and audit logging. This module is only used by the HTTP RPC layer
(http_rpc.py) — the Tauri desktop app uses the Polkit path instead.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from cairn import auth
from cairn.security import (
    AuditEventType,
    RateLimitExceeded,
    audit_log,
    check_rate_limit,
)

logger = logging.getLogger(__name__)


def http_login(
    *,
    username: str,
    credential: str,
    device_id: str | None = None,
    token_db: object | None = None,
) -> dict[str, Any]:
    """Authenticate via PAM and return a session token.

    Rate-limited to 5 attempts per 60 seconds (configured in security.py).
    All attempts are audit-logged regardless of outcome.

    If device_id and token_db are provided, a device refresh token is issued
    and included in the response as "refresh_token".
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

    result = auth.create_session_from_pam(
        username,
        credential,
        device_id=device_id,
        token_db=token_db,
    )

    if result.get("success"):
        audit_log(
            AuditEventType.AUTH_LOGIN_SUCCESS,
            {"username": username, "source": "pwa", "device_id": device_id},
        )
    else:
        audit_log(
            AuditEventType.AUTH_LOGIN_FAILED,
            {"username": username, "source": "pwa"},
        )

    return result


def http_token_refresh(*, refresh_token: str, token_db: object) -> dict[str, Any]:
    """Exchange a device refresh token for a new session.

    Rate-limited to 5 attempts per 60 seconds to prevent token grinding.
    All attempts are audit-logged regardless of outcome.
    """
    try:
        check_rate_limit("token_refresh")
    except RateLimitExceeded as e:
        audit_log(
            AuditEventType.RATE_LIMIT_EXCEEDED,
            {"category": "token_refresh"},
        )
        prefix = hashlib.sha256(refresh_token.encode()).hexdigest()[:8]
        logger.warning("Token refresh rate limit exceeded (prefix=%s)", prefix)
        return {"success": False, "error": str(e)}

    result = auth.refresh_session_from_token(refresh_token, token_db)

    if result.get("success"):
        audit_log(
            AuditEventType.AUTH_TOKEN_REFRESH,
            {"username": result.get("username"), "source": "pwa"},
        )
    else:
        audit_log(
            AuditEventType.AUTH_TOKEN_REFRESH_FAILED,
            {"error": result.get("error"), "source": "pwa"},
            success=False,
        )

    return result


def http_logout(*, session_token: str) -> dict[str, Any]:
    """Invalidate a session."""
    result = auth.logout(session_token)
    if result.get("success"):
        audit_log(AuditEventType.AUTH_LOGOUT, {"source": "pwa"})
    return result
