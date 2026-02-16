"""SQLite DDL and database initialization."""

import sqlite3
from pathlib import Path

ENCOUNTERS_TABLE = """
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
"""

ENCOUNTER_AUDIT_LOG_TABLE = """
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
"""

WORKFLOW_RUNS_TABLE = """
CREATE TABLE IF NOT EXISTS workflow_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    encounter_id TEXT NOT NULL,
    stage TEXT NOT NULL,
    router_output TEXT,
    workflow_output TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (encounter_id) REFERENCES encounters(encounter_id)
);
"""

PRIOR_AUTH_REQUESTS_TABLE = """
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
"""

CLAIM_SUBMISSIONS_TABLE = """
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
"""

ALL_TABLES = [
    ENCOUNTERS_TABLE,
    ENCOUNTER_AUDIT_LOG_TABLE,
    WORKFLOW_RUNS_TABLE,
    PRIOR_AUTH_REQUESTS_TABLE,
    CLAIM_SUBMISSIONS_TABLE,
]


def init_db(db_path: str) -> None:
    """Create database file and all tables if they do not exist."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        for ddl in ALL_TABLES:
            conn.execute(ddl)
        conn.commit()
    finally:
        conn.close()
