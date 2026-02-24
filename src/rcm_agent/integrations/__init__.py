"""Abstractions for external system integration (eligibility, prior auth, claims).

Default implementations are mocks (EligibilityMock, PriorAuthMock, ClaimsMock).
Swap via registry or config (ELIGIBILITY_BACKEND, PRIOR_AUTH_BACKEND, CLAIMS_BACKEND).
"""

from rcm_agent.integrations.claims_mock import ClaimsMock
from rcm_agent.integrations.claims_stub import ClaimsStub
from rcm_agent.integrations.eligibility_mock import EligibilityMock
from rcm_agent.integrations.eligibility_stub import EligibilityStub
from rcm_agent.integrations.prior_auth_mock import PriorAuthMock
from rcm_agent.integrations.prior_auth_stub import PriorAuthStub
from rcm_agent.integrations.protocols import (
    ClaimsBackend,
    EligibilityBackend,
    PriorAuthBackend,
)
from rcm_agent.integrations.registry import (
    get_claims_backend,
    get_eligibility_backend,
    get_prior_auth_backend,
    reset_integration_backends,
)

__all__ = [
    "ClaimsBackend",
    "ClaimsMock",
    "ClaimsStub",
    "EligibilityBackend",
    "EligibilityMock",
    "EligibilityStub",
    "PriorAuthBackend",
    "PriorAuthMock",
    "PriorAuthStub",
    "get_claims_backend",
    "get_eligibility_backend",
    "get_prior_auth_backend",
    "reset_integration_backends",
]
