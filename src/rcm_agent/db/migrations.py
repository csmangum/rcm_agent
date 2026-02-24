"""Simple forward-only schema migration system.

Each migration is a ``(version, description, sql)`` tuple.  The system
tracks applied versions in a ``schema_migrations`` table and applies
any outstanding migrations in order.

To add a new migration, append to ``MIGRATIONS`` with an incremented
version number.
"""

from __future__ import annotations

import sqlite3
from typing import NamedTuple

from rcm_agent.exceptions import MigrationError
from rcm_agent.observability.logging import get_logger

logger = get_logger(__name__)


class Migration(NamedTuple):
    version: int
    description: str
    sql: str


MIGRATIONS: list[Migration] = [
    Migration(
        version=1,
        description="Initial schema — encounters, audit log, workflow runs, prior auth, claims, denials",
        sql="""\
CREATE TABLE IF NOT EXISTS encounters (
    encounter_id TEXT PRIMARY KEY,
    patient TEXT NOT NULL,
    insurance TEXT NOT NULL,
    date TEXT NOT NULL,
    type TEXT NOT NULL,
    procedures TEXT NOT NULL,
    diagnoses TEXT NOT NULL,
    clinical_notes TEXT NOT NULL,
    documents TEXT NOT NULL,
    stage TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_encounters_status ON encounters(status);
CREATE INDEX IF NOT EXISTS idx_encounters_stage ON encounters(stage);

CREATE TABLE IF NOT EXISTS encounter_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    encounter_id TEXT NOT NULL,
    action TEXT NOT NULL,
    old_status TEXT,
    new_status TEXT,
    details TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (encounter_id) REFERENCES encounters(encounter_id)
);
CREATE INDEX IF NOT EXISTS idx_audit_log_encounter_id ON encounter_audit_log(encounter_id);

CREATE TABLE IF NOT EXISTS workflow_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    encounter_id TEXT NOT NULL,
    stage TEXT NOT NULL,
    router_output TEXT,
    workflow_output TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (encounter_id) REFERENCES encounters(encounter_id)
);
CREATE INDEX IF NOT EXISTS idx_workflow_runs_encounter_id ON workflow_runs(encounter_id);

CREATE TABLE IF NOT EXISTS prior_auth_requests (
    auth_id TEXT PRIMARY KEY,
    encounter_id TEXT NOT NULL,
    payer TEXT NOT NULL,
    procedure_codes TEXT NOT NULL,
    clinical_justification TEXT NOT NULL,
    status TEXT NOT NULL,
    submitted_at TEXT NOT NULL,
    decision TEXT,
    decision_date TEXT,
    FOREIGN KEY (encounter_id) REFERENCES encounters(encounter_id)
);
CREATE INDEX IF NOT EXISTS idx_prior_auth_encounter_id ON prior_auth_requests(encounter_id);

CREATE TABLE IF NOT EXISTS claim_submissions (
    claim_id TEXT PRIMARY KEY,
    encounter_id TEXT NOT NULL,
    payer TEXT NOT NULL,
    total_charges REAL NOT NULL,
    icd_codes TEXT NOT NULL,
    cpt_codes TEXT NOT NULL,
    modifiers TEXT NOT NULL,
    status TEXT NOT NULL,
    submitted_at TEXT NOT NULL,
    FOREIGN KEY (encounter_id) REFERENCES encounters(encounter_id)
);
CREATE INDEX IF NOT EXISTS idx_claim_submissions_encounter_id ON claim_submissions(encounter_id);

CREATE TABLE IF NOT EXISTS denial_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    encounter_id TEXT NOT NULL,
    claim_id TEXT,
    payer TEXT,
    reason_codes TEXT NOT NULL,
    denial_type TEXT NOT NULL,
    appeal_viable INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (encounter_id) REFERENCES encounters(encounter_id)
);
CREATE INDEX IF NOT EXISTS idx_denial_events_encounter_id ON denial_events(encounter_id);
CREATE INDEX IF NOT EXISTS idx_denial_events_denial_type ON denial_events(denial_type);
CREATE INDEX IF NOT EXISTS idx_denial_events_payer ON denial_events(payer);
""",
    ),
]


_MIGRATION_TABLE_DDL = """\
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    description TEXT NOT NULL,
    applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
"""


def _ensure_migration_table(conn: sqlite3.Connection) -> None:
    conn.executescript(_MIGRATION_TABLE_DDL)


def _applied_versions(conn: sqlite3.Connection) -> set[int]:
    cur = conn.execute("SELECT version FROM schema_migrations ORDER BY version")
    return {row[0] for row in cur.fetchall()}


def migrate(db_path: str) -> list[int]:
    """Apply all pending migrations to *db_path*.  Returns list of newly-applied version numbers."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        _ensure_migration_table(conn)
        applied = _applied_versions(conn)
        newly_applied: list[int] = []

        for m in sorted(MIGRATIONS, key=lambda m: m.version):
            if m.version in applied:
                continue
            logger.info(
                "Applying migration",
                version=m.version,
                description=m.description,
            )
            try:
                conn.executescript(m.sql)
                conn.execute(
                    "INSERT INTO schema_migrations (version, description) VALUES (?, ?)",
                    (m.version, m.description),
                )
                conn.commit()
                newly_applied.append(m.version)
            except sqlite3.Error as exc:
                conn.rollback()
                raise MigrationError(
                    f"Migration v{m.version} ({m.description}) failed: {exc}"
                ) from exc

        return newly_applied
    finally:
        conn.close()


def current_version(db_path: str) -> int:
    """Return the highest applied migration version, or 0 if none."""
    conn = sqlite3.connect(db_path)
    try:
        _ensure_migration_table(conn)
        cur = conn.execute("SELECT MAX(version) FROM schema_migrations")
        row = cur.fetchone()
        return row[0] or 0
    finally:
        conn.close()
