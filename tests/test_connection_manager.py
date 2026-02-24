"""Tests for the ConnectionManager (db/connection.py)."""

import sqlite3
from pathlib import Path

import pytest

from rcm_agent.db.connection import ConnectionManager
from rcm_agent.exceptions import DatabaseError


@pytest.fixture
def cm(tmp_path: Path) -> ConnectionManager:
    db_path = str(tmp_path / "test_cm.db")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, val TEXT)")
    conn.commit()
    conn.close()
    return ConnectionManager(db_path)


def test_connection_context_yields_connection(cm: ConnectionManager):
    with cm.connection() as conn:
        assert isinstance(conn, sqlite3.Connection)


def test_transaction_auto_commits(cm: ConnectionManager):
    with cm.transaction() as conn:
        conn.execute("INSERT INTO t (val) VALUES (?)", ("hello",))
    with cm.connection() as conn:
        cur = conn.execute("SELECT val FROM t")
        assert cur.fetchone()[0] == "hello"


def test_transaction_rollback_on_error(cm: ConnectionManager):
    with pytest.raises(DatabaseError), cm.transaction() as conn:
        conn.execute("INSERT INTO t (val) VALUES (?)", ("will_rollback",))
        conn.execute("INVALID SQL")
    with cm.connection() as conn:
        cur = conn.execute("SELECT COUNT(*) FROM t WHERE val = ?", ("will_rollback",))
        assert cur.fetchone()[0] == 0


def test_connection_reuses_same_thread(cm: ConnectionManager):
    with cm.connection() as c1:
        pass
    with cm.connection() as c2:
        pass
    assert c1 is c2


def test_close_releases_connection(cm: ConnectionManager):
    with cm.connection() as c1:
        pass
    cm.close()
    with cm.connection() as c2:
        pass
    assert c1 is not c2


def test_connection_foreign_keys_enabled(cm: ConnectionManager):
    with cm.connection() as conn:
        cur = conn.execute("PRAGMA foreign_keys")
        assert cur.fetchone()[0] == 1


def test_invalid_db_path_raises_database_error(tmp_path: Path):
    bad_path = str(tmp_path / "nonexistent_dir" / "sub" / "db.sqlite")
    cm = ConnectionManager(bad_path)
    with pytest.raises(DatabaseError, match="Failed to connect"), cm.connection() as _:
        pass
