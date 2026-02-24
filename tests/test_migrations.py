"""Tests for the database migration system."""

import sqlite3
from pathlib import Path

from rcm_agent.db.migrations import (
    MIGRATIONS,
    current_version,
    migrate,
)


def test_migrate_fresh_db(tmp_path: Path):
    db_path = str(tmp_path / "fresh.db")
    applied = migrate(db_path)
    assert 1 in applied
    assert current_version(db_path) == max(m.version for m in MIGRATIONS)


def test_migrate_creates_all_tables(tmp_path: Path):
    db_path = str(tmp_path / "tables.db")
    migrate(db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = {row[0] for row in cur.fetchall()}
    conn.close()
    expected = {
        "encounters",
        "encounter_audit_log",
        "workflow_runs",
        "prior_auth_requests",
        "claim_submissions",
        "denial_events",
        "schema_migrations",
    }
    assert expected.issubset(tables)


def test_migrate_idempotent(tmp_path: Path):
    db_path = str(tmp_path / "idempotent.db")
    applied1 = migrate(db_path)
    applied2 = migrate(db_path)
    assert len(applied1) > 0
    assert len(applied2) == 0


def test_current_version_fresh_db(tmp_path: Path):
    db_path = str(tmp_path / "version.db")
    assert current_version(db_path) == 0


def test_current_version_after_migration(tmp_path: Path):
    db_path = str(tmp_path / "versioned.db")
    migrate(db_path)
    assert current_version(db_path) >= 1


def test_schema_migrations_table_records(tmp_path: Path):
    db_path = str(tmp_path / "records.db")
    migrate(db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.execute("SELECT version, description FROM schema_migrations ORDER BY version")
    rows = cur.fetchall()
    conn.close()
    assert len(rows) == len(MIGRATIONS)
    assert rows[0][0] == 1
    assert "Initial schema" in rows[0][1]


def test_init_db_uses_migration_system(tmp_path: Path):
    """init_db should create schema_migrations table (i.e. it uses migrations)."""
    from rcm_agent.db.schema import init_db

    db_path = str(tmp_path / "initdb.db")
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'")
    assert cur.fetchone() is not None
    conn.close()
