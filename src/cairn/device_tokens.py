"""Device token storage for mobile refresh-token authentication.

This uses a SEPARATE unencrypted SQLite database because the main
talkingrock.db is SQLCipher-encrypted and requires the very key material
that device tokens exist to recover — a chicken-and-egg problem.

Security: the key_material column stores AES-256-GCM ciphertext wrapped
with a key derived (via HKDF) from the refresh token. Without the raw
token, the stored bytes are indistinguishable from random noise.
"""

from __future__ import annotations

import os
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path


class DeviceTokenStore:
    """Manages device refresh tokens in a separate unencrypted SQLite database.

    Deliberately NOT SQLCipher — this DB must be readable before the main DB
    is unlocked, because it holds the wrapped key material needed to unlock it.
    The key_material column is AES-256-GCM ciphertext (wrapped with a key
    derived from the raw token) so storing it unencrypted at rest is safe.
    """

    def __init__(self, data_dir: str) -> None:
        """Open or create device_tokens.db in the given data directory."""
        db_path = Path(data_dir) / "device_tokens.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db_path = str(db_path)
        self._local = threading.local()
        self._create_schema()

    def _connect(self) -> sqlite3.Connection:
        """Return a thread-local connection, creating one if needed."""
        conn: sqlite3.Connection | None = getattr(self._local, "conn", None)
        if conn is not None:
            return conn
        conn = sqlite3.connect(self._db_path, timeout=5.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA busy_timeout = 5000")
        self._local.conn = conn
        return conn

    def _create_schema(self) -> None:
        """Create tables and indexes if they do not already exist."""
        conn = self._connect()
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS device_tokens (
                id           TEXT PRIMARY KEY,
                device_id    TEXT NOT NULL,
                token_hash   TEXT NOT NULL UNIQUE,
                key_material BLOB NOT NULL,
                username     TEXT NOT NULL,
                created_at   TEXT NOT NULL,
                expires_at   TEXT NOT NULL,
                last_used_at TEXT
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_device_tokens_hash ON device_tokens(token_hash)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_device_tokens_username ON device_tokens(username)"
        )
        conn.commit()

    def insert(
        self,
        *,
        id: str,
        device_id: str,
        token_hash: str,
        key_material: bytes,
        username: str,
        created_at: str,
        expires_at: str,
    ) -> None:
        """Insert a new device token record."""
        conn = self._connect()
        conn.execute(
            """
            INSERT INTO device_tokens
            (id, device_id, token_hash, key_material, username, created_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (id, device_id, token_hash, key_material, username, created_at, expires_at),
        )
        conn.commit()

    def get_by_token_hash(self, token_hash: str) -> dict | None:
        """Return the row matching token_hash, or None if not found."""
        row = self._connect().execute(
            "SELECT * FROM device_tokens WHERE token_hash = ?",
            (token_hash,),
        ).fetchone()
        return dict(row) if row is not None else None

    def touch(self, token_hash: str) -> None:
        """Update last_used_at to now for the given token."""
        now = datetime.now(UTC).isoformat()
        conn = self._connect()
        conn.execute(
            "UPDATE device_tokens SET last_used_at = ? WHERE token_hash = ?",
            (now, token_hash),
        )
        conn.commit()

    def revoke(self, token_hash: str) -> None:
        """Delete the token record for token_hash."""
        conn = self._connect()
        conn.execute(
            "DELETE FROM device_tokens WHERE token_hash = ?",
            (token_hash,),
        )
        conn.commit()

    def revoke_all_for_user(self, username: str) -> None:
        """Delete all token records for the given username."""
        conn = self._connect()
        conn.execute(
            "DELETE FROM device_tokens WHERE username = ?",
            (username,),
        )
        conn.commit()

    def cleanup_expired(self) -> None:
        """Delete all records whose expires_at is in the past."""
        now = datetime.now(UTC).isoformat()
        conn = self._connect()
        conn.execute(
            "DELETE FROM device_tokens WHERE expires_at < ?",
            (now,),
        )
        conn.commit()

    def close(self) -> None:
        """Close the thread-local connection if open."""
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None


# ---------------------------------------------------------------------------
# Module-level singleton — mirrors the pattern used in db.py for Database
# ---------------------------------------------------------------------------

_store_instance: DeviceTokenStore | None = None
_store_lock = threading.Lock()


def _resolve_data_dir() -> str:
    """Resolve the data directory using the same logic as db.py."""
    env = os.environ.get("TALKINGROCK_DATA_DIR")
    if env:
        return env
    # Fall back to the settings object (same as db.py)
    from cairn.settings import settings

    return str(settings.data_dir)


def get_token_store() -> DeviceTokenStore:
    """Get or create the global DeviceTokenStore instance."""
    global _store_instance
    if _store_instance is None:
        with _store_lock:
            if _store_instance is None:
                store = DeviceTokenStore(_resolve_data_dir())
                store.cleanup_expired()
                _store_instance = store
    return _store_instance
