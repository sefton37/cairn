"""Abstract database interface for Claude Code manager.

Allows CCManager to operate without a direct dependency on any specific
database implementation. Cairn provides the concrete implementation
wrapping play_db.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Generator, Protocol, runtime_checkable


@runtime_checkable
class CCDatabase(Protocol):
    """Database adapter for CCManager operations."""

    def get_connection(self) -> sqlite3.Connection:
        """Get a read-only database connection."""
        ...

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager yielding a writable connection that auto-commits."""
        ...
