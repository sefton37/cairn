"""Concrete CCDatabase adapter wrapping Cairn's play_db."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Generator

from cairn.play_db import _get_connection, _transaction


class CairnCCDatabase:
    """CCDatabase implementation backed by Cairn's play_db (talkingrock.db)."""

    def get_connection(self) -> sqlite3.Connection:
        return _get_connection()

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        with _transaction() as conn:
            yield conn
