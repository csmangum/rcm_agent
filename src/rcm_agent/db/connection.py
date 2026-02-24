"""SQLite connection management with context manager and thread-local pooling."""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Generator
from contextlib import contextmanager

from rcm_agent.exceptions import DatabaseError


class ConnectionManager:
    """Thread-safe SQLite connection manager.

    Reuses one connection per thread (SQLite allows one writer at a time,
    so a full pool isn't necessary; thread-local reuse avoids the overhead
    of connect/close on every operation).
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._local = threading.local()

    @property
    def db_path(self) -> str:
        return self._db_path

    def _get_connection(self) -> sqlite3.Connection:
        conn: sqlite3.Connection | None = getattr(self._local, "conn", None)
        if conn is None:
            try:
                conn = sqlite3.connect(self._db_path)
                conn.execute("PRAGMA foreign_keys = ON")
                conn.execute("PRAGMA journal_mode = WAL")
            except sqlite3.Error as exc:
                raise DatabaseError(f"Failed to connect to {self._db_path}: {exc}") from exc
            self._local.conn = conn
        return conn

    @contextmanager
    def connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Yield a connection. For read-only use no commit is needed; for writes
        the caller must commit. On exception the transaction is rolled back."""
        conn = self._get_connection()
        try:
            yield conn
        except sqlite3.Error as exc:
            conn.rollback()
            raise DatabaseError(str(exc)) from exc
        except Exception:
            conn.rollback()
            raise

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        """Yield a connection that auto-commits on clean exit and rolls back
        on any exception."""
        conn = self._get_connection()
        try:
            yield conn
            conn.commit()
        except sqlite3.Error as exc:
            conn.rollback()
            raise DatabaseError(str(exc)) from exc
        except Exception:
            conn.rollback()
            raise

    def close(self) -> None:
        """Close the thread-local connection if one exists."""
        conn: sqlite3.Connection | None = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None
