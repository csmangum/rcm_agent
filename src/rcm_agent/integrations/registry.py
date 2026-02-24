"""Registry for external backends. Implementation selected via config (env or future config file)."""

from rcm_agent.config import get_integrations_config
from rcm_agent.exceptions import ValidationError
from rcm_agent.integrations.claims_mock import ClaimsMock
from rcm_agent.integrations.eligibility_mock import EligibilityMock
from rcm_agent.integrations.http_clients import ClaimsHttpClient, EligibilityHttpClient, PriorAuthHttpClient
from rcm_agent.integrations.prior_auth_mock import PriorAuthMock
from rcm_agent.integrations.protocols import ClaimsBackend, EligibilityBackend, PriorAuthBackend

# Map backend name to implementation class.
# "http" uses mock_server_url from config; add "fhir", "edi", etc. when adapters exist.
_ELIGIBILITY_BACKENDS: dict[str, type[EligibilityBackend]] = {
    "mock": EligibilityMock,
}
_PRIOR_AUTH_BACKENDS: dict[str, type[PriorAuthBackend]] = {
    "mock": PriorAuthMock,
}
_CLAIMS_BACKENDS: dict[str, type[ClaimsBackend]] = {
    "mock": ClaimsMock,
}

_eligibility_backend: EligibilityBackend | None = None
_prior_auth_backend: PriorAuthBackend | None = None
_claims_backend: ClaimsBackend | None = None


def reset_integration_backends() -> None:
    """Clear cached backends (for tests). Next get_* call will read config again."""
    global _eligibility_backend, _prior_auth_backend, _claims_backend
    _eligibility_backend = None
    _prior_auth_backend = None
    _claims_backend = None


def get_eligibility_backend() -> EligibilityBackend:
    """Return the configured eligibility backend (default: mock)."""
    global _eligibility_backend
    if _eligibility_backend is None:
        cfg = get_integrations_config()
        name = cfg["eligibility"]
        if name == "http":
            base_url = cfg.get("mock_server_url", "http://localhost:8000")
            _eligibility_backend = EligibilityHttpClient(base_url)
        else:
            impl = _ELIGIBILITY_BACKENDS.get(name)
            if impl is None:
                raise ValidationError(
                    f"Unknown ELIGIBILITY_BACKEND={name!r}. "
                    f"Supported: {list(_ELIGIBILITY_BACKENDS)}, http. "
                    "Set ELIGIBILITY_BACKEND=mock or add the adapter to the registry."
                )
            _eligibility_backend = impl()
    return _eligibility_backend


def get_prior_auth_backend() -> PriorAuthBackend:
    """Return the configured prior-auth backend (default: mock)."""
    global _prior_auth_backend
    if _prior_auth_backend is None:
        cfg = get_integrations_config()
        name = cfg["prior_auth"]
        if name == "http":
            base_url = cfg.get("mock_server_url", "http://localhost:8000")
            _prior_auth_backend = PriorAuthHttpClient(base_url)
        else:
            impl = _PRIOR_AUTH_BACKENDS.get(name)
            if impl is None:
                raise ValidationError(
                    f"Unknown PRIOR_AUTH_BACKEND={name!r}. "
                    f"Supported: {list(_PRIOR_AUTH_BACKENDS)}, http. "
                    "Set PRIOR_AUTH_BACKEND=mock or add the adapter to the registry."
                )
            _prior_auth_backend = impl()
    return _prior_auth_backend


def get_claims_backend() -> ClaimsBackend:
    """Return the configured claims backend (default: mock)."""
    global _claims_backend
    if _claims_backend is None:
        cfg = get_integrations_config()
        name = cfg["claims"]
        if name == "http":
            base_url = cfg.get("mock_server_url", "http://localhost:8000")
            _claims_backend = ClaimsHttpClient(base_url)
        else:
            impl = _CLAIMS_BACKENDS.get(name)
            if impl is None:
                raise ValidationError(
                    f"Unknown CLAIMS_BACKEND={name!r}. "
                    "Supported: mock, http. "
                    "Set CLAIMS_BACKEND=mock or add the adapter to the registry."
                )
            _claims_backend = impl()
    return _claims_backend
