"""Authentication module for Cairn.

Handles:
- Polkit authentication via native system dialog
- Session token generation
- Encryption key derivation using Scrypt
- Per-user session management

Security Notes:
- Uses Polkit for authentication (freedesktop.org standard)
- Shows native system authentication dialog
- Integrates with PAM, fingerprint, smartcard, etc.
- Encryption keys derived from password, stored only in memory
- Session tokens are 256-bit cryptographically random
"""

from __future__ import annotations

import hashlib
import logging
import os
import secrets
import subprocess
import threading
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import uuid

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

# Session idle timeout (15 minutes)
SESSION_IDLE_TIMEOUT_SECONDS = 15 * 60

# Keyring service name for persistent data-encryption keys
KEYRING_ENCRYPTION_SERVICE = "com.cairn.encryption"


@dataclass
class Session:
    """An authenticated user session."""

    token: str
    username: str
    created_at: datetime
    last_activity: datetime
    key_material: bytes = field(repr=False)  # Never print key material

    def is_expired(self) -> bool:
        """Check if session has expired due to inactivity."""
        elapsed = (datetime.now(UTC) - self.last_activity).total_seconds()
        return elapsed > SESSION_IDLE_TIMEOUT_SECONDS

    def refresh(self) -> None:
        """Update last activity timestamp."""
        self.last_activity = datetime.now(UTC)

    def get_user_data_root(self) -> Path:
        """Get the user's encrypted data directory."""
        return Path.home() / ".talkingrock" / self.username


class SessionStore:
    """Thread-safe session storage."""

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()

    def insert(self, session: Session) -> None:
        """Store a new session."""
        with self._lock:
            self._sessions[session.token] = session

    def get(self, token: str) -> Session | None:
        """Get a session by token (if valid and not expired)."""
        with self._lock:
            session = self._sessions.get(token)
            if session and not session.is_expired():
                return session
            return None

    def remove(self, token: str) -> bool:
        """Remove and invalidate a session."""
        with self._lock:
            if token in self._sessions:
                # Clear key material before removing
                session = self._sessions[token]
                # Overwrite key material with zeros
                if session.key_material:
                    zeros = bytes(len(session.key_material))
                    session.key_material = zeros
                del self._sessions[token]
                return True
            return False

    def refresh(self, token: str) -> bool:
        """Refresh a session's activity timestamp."""
        with self._lock:
            session = self._sessions.get(token)
            if session and not session.is_expired():
                session.refresh()
                return True
            return False

    def cleanup_expired(self) -> int:
        """Remove all expired sessions. Returns count of removed sessions."""
        with self._lock:
            expired = [t for t, s in self._sessions.items() if s.is_expired()]
            for token in expired:
                session = self._sessions[token]
                if session.key_material:
                    zeros = bytes(len(session.key_material))
                    session.key_material = zeros
                del self._sessions[token]
            return len(expired)


# Global session store (thread-safe)
_session_store = SessionStore()


def get_session_store() -> SessionStore:
    """Get the global session store."""
    return _session_store


REFRESH_TOKEN_EXPIRY_DAYS = 90
_WRAP_INFO = b"cairn-device-token-key-wrap-v1"


def generate_refresh_token() -> str:
    """Generate a cryptographically secure refresh token.

    Returns:
        64-character hex string (256 bits of entropy)
    """
    return secrets.token_hex(32)


def _hash_token(raw_token: str) -> str:
    """Return the SHA-256 hex digest of the raw token string."""
    return hashlib.sha256(raw_token.encode()).hexdigest()


_WRAP_SALT = b"cairn-device-token-wrap-salt-v1"


def _derive_wrapping_key(raw_token: str) -> bytes:
    """Derive a 256-bit wrapping key from the raw token.

    Uses HKDF-SHA256 with a fixed domain-separation salt so the wrapping
    key is distinct from the token value and is bound to a context string
    that cannot be reused elsewhere.
    """
    hkdf = HKDF(
        algorithm=SHA256(),
        length=32,
        salt=_WRAP_SALT,
        info=_WRAP_INFO,
    )
    return hkdf.derive(bytes.fromhex(raw_token))


def wrap_key_material(key_material: bytes, raw_token: str) -> bytes:
    """Encrypt key_material with a key derived from raw_token.

    Returns:
        nonce (12 bytes) || ciphertext+tag (48 bytes) = 60 bytes total
    """
    wrapping_key = _derive_wrapping_key(raw_token)
    aesgcm = AESGCM(wrapping_key)
    nonce = os.urandom(12)
    ct = aesgcm.encrypt(nonce, key_material, None)
    return nonce + ct  # 12 + 48 = 60 bytes


def unwrap_key_material(encrypted: bytes, raw_token: str) -> bytes:
    """Decrypt key_material previously wrapped with wrap_key_material().

    Raises:
        cryptography.exceptions.InvalidTag: if the token is wrong or data is corrupted
    """
    wrapping_key = _derive_wrapping_key(raw_token)
    aesgcm = AESGCM(wrapping_key)
    nonce, ct = encrypted[:12], encrypted[12:]
    return aesgcm.decrypt(nonce, ct, None)


def create_device_token(
    username: str,
    key_material: bytes,
    device_id: str,
    token_db: object,
) -> str:
    """Generate a device refresh token and persist it in token_db.

    The raw key_material is AES-256-GCM wrapped before storage so the
    device_tokens.db (plain SQLite) stores only ciphertext.

    Args:
        username:     Linux username this token belongs to.
        key_material: The 32-byte encryption key to protect.
        device_id:    Opaque device identifier supplied by the client.
        token_db:     A DeviceTokenStore instance.

    Returns:
        The raw 64-hex-char refresh token to return to the client.
        Never stored by the server.
    """
    from datetime import timedelta

    raw = generate_refresh_token()
    raw_hash = _hash_token(raw)
    wrapped = wrap_key_material(key_material, raw)

    now = datetime.now(UTC)
    token_db.insert(  # type: ignore[union-attr]
        id=uuid.uuid4().hex,
        device_id=device_id,
        token_hash=raw_hash,
        key_material=wrapped,
        username=username,
        created_at=now.isoformat(),
        expires_at=(now + timedelta(days=REFRESH_TOKEN_EXPIRY_DAYS)).isoformat(),
    )
    return raw


def refresh_session_from_token(raw_token: str, token_db: object) -> dict[str, Any]:
    """Exchange a device refresh token for a new session.

    Looks up the token, verifies expiry, unwraps the key_material, creates a
    Session, and wires up the crypto layer — replicating exactly what
    create_session_from_pam() does after PAM succeeds.

    Args:
        raw_token: The raw token previously issued to the device.
        token_db:  A DeviceTokenStore instance.

    Returns:
        {"success": True, "session_token": ..., "username": ...} on success,
        or {"success": False, "error": ...} on any failure.
    """
    from cryptography.exceptions import InvalidTag

    from . import db_crypto

    raw_hash = _hash_token(raw_token)
    row = token_db.get_by_token_hash(raw_hash)  # type: ignore[union-attr]

    if row is None:
        logger.warning("Device token not found for hash %s", raw_hash[:8])
        return {"success": False, "error": "Token not found or already revoked"}

    # Check expiry
    expires_at = datetime.fromisoformat(row["expires_at"])
    if expires_at.tzinfo is None:
        logger.warning("expires_at for device token has no timezone — assuming UTC")
        expires_at = expires_at.replace(tzinfo=UTC)
    if datetime.now(UTC) >= expires_at:
        logger.warning("Expired device token used by %s", row["username"])
        token_db.revoke(raw_hash)  # type: ignore[union-attr]
        return {"success": False, "error": "Refresh token has expired"}

    # Unwrap key material
    try:
        key_material = unwrap_key_material(row["key_material"], raw_token)
    except InvalidTag:
        logger.warning("Device token unwrap failed — invalid token for %s", row["username"])
        return {"success": False, "error": "Invalid token"}
    except Exception as e:
        logger.error("Device token unwrap error: %s", e)
        return {"success": False, "error": "Token validation failed"}

    # Build a new Session
    session_val = generate_session_token()
    now = datetime.now(UTC)
    session = Session(
        token=session_val,
        username=row["username"],
        created_at=now,
        last_activity=now,
        key_material=key_material,
    )
    _session_store.insert(session)

    # Wire up the crypto layer (same post-auth setup as create_session_from_pam)
    db_crypto.set_active_key(key_material)

    from .crypto_storage import CryptoStorage, set_active_crypto

    set_active_crypto(CryptoStorage(session))

    # Ensure user data directory exists
    user_data_root = session.get_user_data_root()
    user_data_root.mkdir(parents=True, exist_ok=True)

    # Update last-used timestamp on the token record
    token_db.touch(raw_hash)  # type: ignore[union-attr]

    logger.info("Device token refresh succeeded for %s", row["username"])
    return {"success": True, "session_token": session_val, "username": row["username"]}


def authenticate_polkit(username: str) -> bool:
    """Authenticate user via Polkit (native system dialog).

    This shows the system's native authentication dialog, which:
    - Integrates with PAM for password verification
    - Supports fingerprint, smartcard, and other auth methods
    - Is the freedesktop.org standard for desktop authentication
    - Is what Linux users expect from native applications

    Uses the com.reos.authenticate polkit action which always requires
    authentication (auth_self), even if the user is already logged in.

    Args:
        username: Linux username to authenticate

    Returns:
        True if authentication succeeded, False otherwise

    Security:
        - Uses pkcheck with custom polkit action
        - No password handling in our code
        - System handles all credential verification
    """
    try:
        # Ensure required environment variables are passed for Polkit dialog
        env = os.environ.copy()

        # These are required for the Polkit agent to show the dialog
        uid = os.getuid()
        if "DISPLAY" not in env:
            env["DISPLAY"] = ":0"
        if "XDG_RUNTIME_DIR" not in env:
            env["XDG_RUNTIME_DIR"] = f"/run/user/{uid}"
        if "DBUS_SESSION_BUS_ADDRESS" not in env:
            env["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path=/run/user/{uid}/bus"

        # Get the process ID for pkcheck
        pid = os.getpid()

        # Use pkcheck to trigger authentication for our custom action
        # --action-id: our custom polkit action that requires auth_self
        # --process: the current process
        # --allow-user-interaction: show the auth dialog
        result = subprocess.run(
            [
                "pkcheck",
                "--action-id",
                "com.reos.authenticate",
                "--process",
                str(pid),
                "--allow-user-interaction",
            ],
            capture_output=True,
            timeout=120,  # 2 minute timeout for user to authenticate
            env=env,
        )

        return result.returncode == 0
    except subprocess.TimeoutExpired:
        logger.warning("Polkit authentication timed out")
        return False
    except Exception as e:
        logger.warning("Polkit authentication failed: %s", e)
        return False


def derive_encryption_key(username: str, password: str) -> bytes:
    """Derive a 256-bit encryption key from username and password.

    Uses Scrypt for key derivation (memory-hard, side-channel resistant).

    Args:
        username: Linux username (used as salt basis)
        password: User's password

    Returns:
        32-byte encryption key

    Security:
        - Salt is deterministic per-user to allow key recovery
        - Scrypt parameters tuned for security vs. responsiveness
    """
    # Create deterministic salt from username
    salt_input = f"reos-{username}-encryption-salt-v1"
    salt = hashlib.sha256(salt_input.encode()).digest()[:16]

    # Scrypt parameters (memory-hard)
    # - N=2^14 (16384): Memory cost
    # - r=8: Block size
    # - p=1: Parallelization
    kdf = Scrypt(
        salt=salt,
        length=32,
        n=16384,
        r=8,
        p=1,
    )

    return kdf.derive(password.encode())


def generate_session_token() -> str:
    """Generate a cryptographically secure session token.

    Returns:
        64-character hex string (256 bits)
    """
    return secrets.token_hex(32)


def _get_or_create_dek(username: str) -> bytes:
    """Get or create a persistent data-encryption key via system keyring.

    On first Polkit login, generates a 256-bit DEK and stores it in the
    system keyring. On subsequent logins, retrieves the existing key.

    Falls back to a random (non-persistent) key if the keyring is
    unavailable (headless, no D-Bus), matching the existing graceful
    degradation pattern in providers/secrets.py.

    Args:
        username: Linux username (keyring entry name).

    Returns:
        32-byte data-encryption key.
    """
    import base64

    try:
        import keyring

        stored = keyring.get_password(KEYRING_ENCRYPTION_SERVICE, username)
        if stored:
            logger.debug("Retrieved existing DEK from keyring for %s", username)
            return base64.b64decode(stored)

        # First login: generate and persist
        dek = secrets.token_bytes(32)
        keyring.set_password(
            KEYRING_ENCRYPTION_SERVICE,
            username,
            base64.b64encode(dek).decode("ascii"),
        )
        logger.info("Generated and stored new DEK in keyring for %s", username)
        return dek

    except Exception as e:
        logger.warning(
            "System keyring unavailable, using ephemeral key (CryptoStorage "
            "will not persist across sessions): %s",
            e,
        )
        return secrets.token_bytes(32)


def create_session_polkit(username: str) -> Session | None:
    """Authenticate user via Polkit and create a new session.

    Note: Since Polkit handles authentication without exposing the password,
    we cannot derive an encryption key from it. For encrypted storage,
    a separate key setup step would be needed.

    Args:
        username: Linux username

    Returns:
        Session if authentication succeeded, None otherwise
    """
    # Authenticate via Polkit (shows system dialog)
    if not authenticate_polkit(username):
        return None

    # Generate session credential
    session_token = generate_session_token()
    now = datetime.now(UTC)

    # Retrieve or create a persistent DEK via system keyring
    key_material = _get_or_create_dek(username)

    return Session(
        token=session_token,
        username=username,
        created_at=now,
        last_activity=now,
        key_material=key_material,
    )


def login_polkit(username: str) -> dict[str, Any]:
    """Authenticate via Polkit and create a session.

    Shows the native system authentication dialog.

    Args:
        username: Linux username

    Returns:
        Dict with success status, session_token, username, or error
    """
    from . import db_crypto

    # Validate username format
    if not username or len(username) > 32:
        return {
            "success": False,
            "error": "Invalid username",
        }

    # Basic username validation (Linux username rules)
    if not all(c.isalnum() or c in "_-" for c in username):
        return {
            "success": False,
            "error": "Invalid username format",
        }

    # Create session (authenticates via Polkit)
    session = create_session_polkit(username)

    if session is None:
        return {
            "success": False,
            "error": "Authentication cancelled or failed",
        }

    # Store session
    _session_store.insert(session)

    # Make DEK available to database layer
    db_crypto.set_active_key(session.key_material)

    # Initialize CryptoStorage for file encryption
    from .crypto_storage import CryptoStorage, set_active_crypto

    set_active_crypto(CryptoStorage(session))

    # Ensure user data directory exists
    user_data_root = session.get_user_data_root()
    user_data_root.mkdir(parents=True, exist_ok=True)

    return {
        "success": True,
        "session_token": session.token,
        "username": session.username,
    }


def create_session_from_pam(
    username: str,
    credential: str,
    device_id: str | None = None,
    token_db: object | None = None,
) -> dict[str, Any]:
    """Authenticate via PAM and create a session.

    This is the HTTP/PWA auth path. Unlike authenticate_polkit() which shows
    a native GUI dialog, this validates credentials directly via python-pam —
    the same underlying PAM stack, different invocation mechanism.

    Advantage over Polkit: since we have the password, we can derive a real
    encryption key via Scrypt instead of using a random placeholder.

    If device_id and token_db are both provided, a device refresh token is
    issued and returned in the response as "refresh_token". Token creation
    failure is non-fatal — the session is still returned.

    Called by rpc_handlers/http_auth.py. Never called by the Tauri path.
    """
    import pam as pam_lib

    from . import db_crypto

    # Validate username format (same rules as login_polkit)
    if not username or len(username) > 32:
        return {"success": False, "error": "Invalid username"}
    if not all(c.isalnum() or c in "_-" for c in username):
        return {"success": False, "error": "Invalid username format"}

    p = pam_lib.pam()
    if not p.authenticate(username, credential):
        logger.warning("PAM auth failed for %s: %s", username, p.reason)
        return {"success": False, "error": "Authentication failed"}

    # Derive real encryption key from credentials (Scrypt)
    key_material = derive_encryption_key(username, credential)

    session_val = generate_session_token()
    now = datetime.now(UTC)

    session = Session(
        token=session_val,
        username=username,
        created_at=now,
        last_activity=now,
        key_material=key_material,
    )
    _session_store.insert(session)

    # Make DEK available to database layer
    db_crypto.set_active_key(session.key_material)

    # Initialize CryptoStorage for file encryption
    from .crypto_storage import CryptoStorage, set_active_crypto

    set_active_crypto(CryptoStorage(session))

    # Ensure user data directory exists
    user_data_root = session.get_user_data_root()
    user_data_root.mkdir(parents=True, exist_ok=True)

    logger.info("PAM session created for %s", username)
    result: dict[str, Any] = {
        "success": True,
        "session_token": session.token,
        "username": session.username,
    }

    # Optionally issue a device refresh token (non-fatal on failure)
    if device_id is not None and token_db is not None:
        try:
            refresh = create_device_token(username, key_material, device_id, token_db)
            result["refresh_token"] = refresh
        except Exception as e:
            logger.error("Device token creation failed for %s: %s", username, e)

    return result


# Keep old function name for compatibility
def login(username: str, password: str | None = None) -> dict[str, Any]:
    """Authenticate and create a session.

    Uses Polkit for authentication (password parameter is ignored).

    Args:
        username: Linux username
        password: Ignored - Polkit handles authentication

    Returns:
        Dict with success status, session_token, username, or error
    """
    return login_polkit(username)


def logout(session_token: str) -> dict[str, Any]:
    """Destroy a session.

    Args:
        session_token: The session token to invalidate

    Returns:
        Dict with success status
    """
    from . import db_crypto

    if _session_store.remove(session_token):
        # Clear encryption state from memory when last session ends
        db_crypto.set_active_key(None)
        from .crypto_storage import set_active_crypto

        set_active_crypto(None)
        return {"success": True}
    return {"success": False, "error": "Session not found"}


def validate_session(session_token: str) -> dict[str, Any]:
    """Validate a session token.

    Args:
        session_token: The session token to validate

    Returns:
        Dict with valid status and session info if valid
    """
    session = _session_store.get(session_token)
    if session:
        return {
            "valid": True,
            "username": session.username,
        }
    return {"valid": False}


def get_session(session_token: str) -> Session | None:
    """Get a session by token.

    Args:
        session_token: The session token

    Returns:
        Session if valid, None otherwise
    """
    return _session_store.get(session_token)


def refresh_session(session_token: str) -> bool:
    """Refresh a session's activity timestamp.

    Args:
        session_token: The session token

    Returns:
        True if session was refreshed, False if not found/expired
    """
    return _session_store.refresh(session_token)


# Encryption utilities using session key


def encrypt_data(session: Session, plaintext: bytes) -> bytes:
    """Encrypt data using the session's encryption key.

    Args:
        session: The authenticated session
        plaintext: Data to encrypt

    Returns:
        Encrypted data (nonce || ciphertext)
    """
    cipher = AESGCM(session.key_material)
    nonce = os.urandom(12)
    ciphertext = cipher.encrypt(nonce, plaintext, None)
    return nonce + ciphertext


def decrypt_data(session: Session, encrypted: bytes) -> bytes:
    """Decrypt data using the session's encryption key.

    Args:
        session: The authenticated session
        encrypted: Encrypted data (nonce || ciphertext)

    Returns:
        Decrypted plaintext

    Raises:
        ValueError: If decryption fails (wrong key or corrupted data)
    """
    if len(encrypted) < 12:
        raise ValueError("Invalid encrypted data: too short")

    cipher = AESGCM(session.key_material)
    nonce = encrypted[:12]
    ciphertext = encrypted[12:]
    return cipher.decrypt(nonce, ciphertext, None)
