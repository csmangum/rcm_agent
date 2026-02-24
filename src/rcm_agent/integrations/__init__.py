"""Abstractions for external system integration (eligibility, prior auth, claims).

Implementations can be mock (default), FHIR, EDI, or payer-specific APIs.
Use a registry or config (e.g. ELIGIBILITY_BACKEND, PRIOR_AUTH_BACKEND) to swap backends.
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
