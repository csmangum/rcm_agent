"""Registry for external backends. Implementation selected via config (env or future config file)."""

from rcm_agent.config import get_integrations_config
from rcm_agent.integrations.eligibility_mock import EligibilityMock
from rcm_agent.integrations.http_clients import EligibilityHttpClient, PriorAuthHttpClient
from rcm_agent.integrations.prior_auth_mock import PriorAuthMock
from rcm_agent.integrations.protocols import EligibilityBackend, PriorAuthBackend

# Map backend name (from ELIGIBILITY_BACKEND / PRIOR_AUTH_BACKEND) to implementation class.
# "http" uses mock_server_url from config; add "fhir", "edi", etc. when adapters exist.
_ELIGIBILITY_BACKENDS: dict[str, type[EligibilityBackend]] = {
    "mock": EligibilityMock,
}
_PRIOR_AUTH_BACKENDS: dict[str, type[PriorAuthBackend]] = {
    "mock": PriorAuthMock,
}

_eligibility_backend: EligibilityBackend | None = None
_prior_auth_backend: PriorAuthBackend | None = None


def reset_integration_backends() -> None:
    """Clear cached backends (for tests). Next get_* call will read config again."""
    global _eligibility_backend, _prior_auth_backend
    _eligibility_backend = None
    _prior_auth_backend = None


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
                raise ValueError(
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
                raise ValueError(
                    f"Unknown PRIOR_AUTH_BACKEND={name!r}. "
                    f"Supported: {list(_PRIOR_AUTH_BACKENDS)}, http. "
                    "Set PRIOR_AUTH_BACKEND=mock or add the adapter to the registry."
                )
            _prior_auth_backend = impl()
    return _prior_auth_backend
