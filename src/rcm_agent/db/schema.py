"""Database initialization via the migration system.

Callers should use ``init_db(db_path)`` which delegates to the migration
system.  The raw DDL constants are kept for backward-compatibility but
the canonical schema lives in ``migrations.py``.
"""

from pathlib import Path

from rcm_agent.db.migrations import migrate


def init_db(db_path: str) -> None:
    """Create database file and apply all pending migrations."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    migrate(db_path)
