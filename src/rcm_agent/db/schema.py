"""Database initialization via the migration system.

Callers should use ``init_db(db_path)`` which delegates to the migration
system; the canonical schema lives in :mod:`rcm_agent.db.migrations`.
"""

from pathlib import Path

from rcm_agent.db.migrations import migrate


def init_db(db_path: str) -> None:
    """Create database file and apply all pending migrations."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    migrate(db_path)
