"""Abstractions for external system integration (eligibility, prior auth, claims).

Implementations can be mock (default), FHIR, EDI, or payer-specific APIs.
Planned: swap backends via registry or config (e.g. ELIGIBILITY_BACKEND, PRIOR_AUTH_BACKEND).
"""

from rcm_agent.integrations.claims_stub import ClaimsStub
from rcm_agent.integrations.protocols import (
    ClaimsBackend,
    EligibilityBackend,
    PriorAuthBackend,
)

__all__ = [
    "ClaimsBackend",
    "ClaimsStub",
    "EligibilityBackend",
    "PriorAuthBackend",
]
