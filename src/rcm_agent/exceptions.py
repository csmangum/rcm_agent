"""Custom exception hierarchy for the RCM Agent.

All domain-specific exceptions inherit from RcmAgentError so callers can
catch broadly (``except RcmAgentError``) or narrowly (``except BackendError``).
"""

from __future__ import annotations


class RcmAgentError(Exception):
    """Base exception for all RCM Agent errors."""

    def __init__(self, message: str, *, encounter_id: str | None = None) -> None:
        self.encounter_id = encounter_id
        super().__init__(message)


class BackendError(RcmAgentError):
    """An external backend (HTTP, mock, FHIR, etc.) returned an error or was unreachable."""

    def __init__(
        self,
        message: str,
        *,
        encounter_id: str | None = None,
        backend: str | None = None,
        status_code: int | None = None,
    ) -> None:
        self.backend = backend
        self.status_code = status_code
        super().__init__(message, encounter_id=encounter_id)


class RoutingError(RcmAgentError):
    """Router failed to classify an encounter into an RCM stage."""


class ValidationError(RcmAgentError):
    """Encounter or payload data failed domain validation."""


class DatabaseError(RcmAgentError):
    """Database operation failed (connection, query, migration, etc.)."""


class MigrationError(DatabaseError):
    """Schema migration failed."""
