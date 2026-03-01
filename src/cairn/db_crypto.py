"""Encryption-aware database connection factory.

Provides a drop-in replacement for ``sqlite3.connect()`` that transparently
uses SQLCipher when available and a key is provided.  Falls back to plain
``sqlite3`` (with a warning) when ``pysqlcipher3`` is not installed or no
key is supplied.

Key threading
-------------
The active data-encryption key (DEK) is set once after login via
``set_active_key()`` and retrieved by database classes via ``get_active_key()``.

Migration
---------
``migrate_to_encrypted()`` performs a one-time conversion from a plaintext
SQLite database to an encrypted SQLCipher database using ``sqlcipher_export``.
A marker file (``<data_dir>/.encrypted``) prevents re-running the migration.
"""

from __future__ import annotations

import logging
import os
import shutil
import sqlite3
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SQLCipher availability
# ---------------------------------------------------------------------------

_sqlcipher_available = False
_sqlcipher_module = None

try:
    from pysqlcipher3 import dbapi2 as _sqlcipher_module  # type: ignore[import-untyped]

    _sqlcipher_available = True
    logger.debug("pysqlcipher3 available — encrypted databases enabled")
except ImportError:
    logger.warning(
        "pysqlcipher3 not installed — databases will remain unencrypted. "
        "Install with: pip install pysqlcipher3  (requires libsqlcipher-dev)"
    )

# ---------------------------------------------------------------------------
# Active key threading
# ---------------------------------------------------------------------------

_key_lock = threading.Lock()
_active_key: bytes | None = None


def set_active_key(key: bytes | None) -> None:
    """Set the data-encryption key for the current process.

    Called by ``auth.py`` after successful login.  Pass ``None`` on logout
    to clear the key from memory.
    """
    global _active_key
    with _key_lock:
        _active_key = key


def get_active_key() -> bytes | None:
    """Return the current DEK, or ``None`` if not yet authenticated."""
    with _key_lock:
        return _active_key


def is_encrypted_available() -> bool:
    """Return ``True`` if SQLCipher bindings are importable."""
    return _sqlcipher_available


# ---------------------------------------------------------------------------
# Connection factory
# ---------------------------------------------------------------------------


def connect(
    db_path: str,
    key: bytes | None = None,
    **kwargs,
) -> sqlite3.Connection:
    """Open a database connection, optionally encrypted.

    Parameters
    ----------
    db_path:
        Path to the SQLite file (or ``:memory:``).
    key:
        32-byte DEK.  If ``None``, the active key from ``get_active_key()``
        is used.  If still ``None``, a plain ``sqlite3`` connection is
        returned.
    **kwargs:
        Forwarded to ``sqlite3.connect`` / ``sqlcipher.connect``.

    Returns
    -------
    sqlite3.Connection
        A standard ``sqlite3.Connection`` (possibly backed by SQLCipher).
    """
    if key is None:
        key = get_active_key()

    if key and _sqlcipher_available and _sqlcipher_module is not None:
        conn = _sqlcipher_module.connect(db_path, **kwargs)
        # Hex-encode the key for the PRAGMA (SQLCipher expects a hex blob
        # prefixed with ``x'...'``).
        hex_key = key.hex()
        conn.execute(f"PRAGMA key = \"x'{hex_key}'\"")
        return conn

    # Fallback: plain sqlite3
    if key and not _sqlcipher_available:
        logger.debug(
            "Key provided but pysqlcipher3 unavailable — opening %s unencrypted",
            db_path,
        )

    return sqlite3.connect(db_path, **kwargs)


# ---------------------------------------------------------------------------
# Migration: plaintext → encrypted
# ---------------------------------------------------------------------------

_ENCRYPTED_MARKER = ".encrypted"


def _marker_path(db_path: str) -> Path:
    """Return the marker file path for the given database."""
    return Path(db_path).parent / _ENCRYPTED_MARKER


def needs_migration(db_path: str) -> bool:
    """Return ``True`` if *db_path* exists, is plaintext, and has no marker."""
    p = Path(db_path)
    return (
        p.exists()
        and p.stat().st_size > 0
        and not _marker_path(db_path).exists()
    )


def migrate_to_encrypted(db_path: str, key: bytes) -> bool:
    """Convert an existing plaintext database to SQLCipher in-place.

    Steps:
      1. Open the plaintext DB with standard ``sqlite3``.
      2. Attach a new encrypted DB via SQLCipher.
      3. ``sqlcipher_export`` copies all data atomically.
      4. Replace the original file and write a marker.

    Returns ``True`` on success, ``False`` on skip/failure.
    """
    if not _sqlcipher_available or _sqlcipher_module is None:
        logger.warning("Cannot migrate %s — pysqlcipher3 not available", db_path)
        return False

    if not needs_migration(db_path):
        return False

    db = Path(db_path)
    backup = db.with_suffix(".db.bak")
    encrypted = db.with_suffix(".db.enc")

    try:
        # 1. Back up original
        shutil.copy2(db, backup)
        logger.info("Backed up %s → %s", db, backup)

        # 2. Open plaintext with SQLCipher (no key = plaintext mode)
        conn = _sqlcipher_module.connect(str(db))

        # 3. Attach encrypted target
        hex_key = key.hex()
        conn.execute(f"ATTACH DATABASE '{encrypted}' AS encrypted KEY \"x'{hex_key}'\"")

        # 4. Export
        conn.execute("SELECT sqlcipher_export('encrypted')")
        conn.execute("DETACH DATABASE encrypted")
        conn.close()

        # 5. Atomic swap
        encrypted.replace(db)

        # 6. Write marker
        marker = _marker_path(db_path)
        marker.write_text("migrated\n")

        # 7. Tighten permissions
        os.chmod(db, 0o600)
        os.chmod(marker, 0o600)

        logger.info("Successfully migrated %s to encrypted SQLCipher", db)
        return True

    except Exception:
        logger.exception("Migration of %s failed — restoring backup", db_path)
        # Restore backup on any failure
        if backup.exists():
            shutil.copy2(backup, db)
        # Clean up partial encrypted file
        if encrypted.exists():
            encrypted.unlink()
        return False
