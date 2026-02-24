"""SQLite persistence, audit trail, and migrations."""

from rcm_agent.db.connection import ConnectionManager
from rcm_agent.db.migrations import current_version, migrate
from rcm_agent.db.repository import EncounterRepository
from rcm_agent.db.schema import init_db

__all__ = [
    "ConnectionManager",
    "EncounterRepository",
    "current_version",
    "init_db",
    "migrate",
]
