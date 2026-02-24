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

INDEX_ENCOUNTERS_STATUS = "CREATE INDEX IF NOT EXISTS idx_encounters_status ON encounters(status);"
INDEX_ENCOUNTERS_STAGE = "CREATE INDEX IF NOT EXISTS idx_encounters_stage ON encounters(stage);"

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

INDEX_AUDIT_LOG_ENCOUNTER_ID = (
    "CREATE INDEX IF NOT EXISTS idx_audit_log_encounter_id ON encounter_audit_log(encounter_id);"
)

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

INDEX_WORKFLOW_RUNS_ENCOUNTER_ID = (
    "CREATE INDEX IF NOT EXISTS idx_workflow_runs_encounter_id ON workflow_runs(encounter_id);"
)

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

INDEX_PRIOR_AUTH_ENCOUNTER_ID = (
    "CREATE INDEX IF NOT EXISTS idx_prior_auth_encounter_id ON prior_auth_requests(encounter_id);"
)

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

INDEX_CLAIM_SUBMISSIONS_ENCOUNTER_ID = (
    "CREATE INDEX IF NOT EXISTS idx_claim_submissions_encounter_id ON claim_submissions(encounter_id);"
)

DENIAL_EVENTS_TABLE = """
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
"""

INDEX_DENIAL_EVENTS_ENCOUNTER_ID = (
    "CREATE INDEX IF NOT EXISTS idx_denial_events_encounter_id ON denial_events(encounter_id);"
)
INDEX_DENIAL_EVENTS_DENIAL_TYPE = (
    "CREATE INDEX IF NOT EXISTS idx_denial_events_denial_type ON denial_events(denial_type);"
)
INDEX_DENIAL_EVENTS_PAYER = "CREATE INDEX IF NOT EXISTS idx_denial_events_payer ON denial_events(payer);"

ALL_TABLES = [
    ENCOUNTERS_TABLE,
    INDEX_ENCOUNTERS_STATUS,
    INDEX_ENCOUNTERS_STAGE,
    ENCOUNTER_AUDIT_LOG_TABLE,
    INDEX_AUDIT_LOG_ENCOUNTER_ID,
    WORKFLOW_RUNS_TABLE,
    INDEX_WORKFLOW_RUNS_ENCOUNTER_ID,
    PRIOR_AUTH_REQUESTS_TABLE,
    INDEX_PRIOR_AUTH_ENCOUNTER_ID,
    CLAIM_SUBMISSIONS_TABLE,
    INDEX_CLAIM_SUBMISSIONS_ENCOUNTER_ID,
    DENIAL_EVENTS_TABLE,
    INDEX_DENIAL_EVENTS_ENCOUNTER_ID,
    INDEX_DENIAL_EVENTS_DENIAL_TYPE,
    INDEX_DENIAL_EVENTS_PAYER,
]


def init_db(db_path: str) -> None:
    """Create database file and all tables if they do not exist."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        for ddl in ALL_TABLES:
            conn.execute(ddl)
        conn.commit()
    finally:
        conn.close()
