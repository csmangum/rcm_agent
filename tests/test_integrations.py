"""Tests for integration protocols, stub implementations, and config-driven backend selection."""

import os

import pytest

from rcm_agent.config import get_integrations_config
from rcm_agent.integrations import (
    ClaimsBackend,
    ClaimsStub,
    EligibilityBackend,
    EligibilityMock,
    get_eligibility_backend,
    get_prior_auth_backend,
    reset_integration_backends,
)


# --- ClaimsStub behavior ---


def test_claims_stub_submit_claim_returns_stub_response():
    stub = ClaimsStub()
    r = stub.submit_claim({})
    assert r["stub"] is True
    assert r["operation"] == "submit_claim"
    assert r["claim_id"] is None
    assert r["status"] == "stub"
    assert "message" in r


def test_claims_stub_get_remit_returns_stub_response():
    stub = ClaimsStub()
    r = stub.get_remit("some-id")
    assert r["stub"] is True
    assert r["operation"] == "get_remit"
    assert r["claim_id"] == "some-id"
    assert r["payment"] is None
    assert r["adjustments"] == []
    assert "message" in r


# --- Protocol conformance ---


def _run_submit(backend: ClaimsBackend) -> dict:
    """Accept any ClaimsBackend; used to verify structural conformance."""
    return backend.submit_claim({})


def test_claims_stub_conforms_to_claims_backend_protocol():
    stub = ClaimsStub()
    r = _run_submit(stub)
    assert r["stub"] is True
    assert r["operation"] == "submit_claim"


def test_claims_stub_isinstance_claims_backend():
    stub = ClaimsStub()
    assert isinstance(stub, ClaimsBackend)


# --- Interface swap: alternate EligibilityBackend ---


class AlwaysIneligibleEligibilityBackend:
    """Minimal alternate mock that always returns not eligible."""

    def check_member_eligibility(
        self, payer: str, member_id: str, date_of_service: str
    ) -> dict:
        return {
            "eligible": False,
            "plan_name": "Test Plan",
            "effective_date": None,
            "termination_date": None,
            "in_network": True,
            "member_status": "terminated",
            "date_of_service": date_of_service,
        }

    def verify_benefits(
        self, payer: str, member_id: str, procedure_codes: list[str]
    ) -> dict:
        return {
            "payer": payer,
            "member_id": member_id,
            "procedures": [
                {
                    "procedure_code": code,
                    "covered": False,
                    "copay": None,
                    "coinsurance_pct": None,
                    "deductible_remaining": None,
                }
                for code in procedure_codes
            ],
        }


def _check_eligible(backend: EligibilityBackend, payer: str, member_id: str) -> bool:
    """Use backend via protocol; demonstrates swap-ability."""
    result = backend.check_member_eligibility(payer, member_id, "2026-01-01")
    return result.get("eligible", False)


def test_eligibility_backend_swap_different_outcomes():
    default_mock = get_eligibility_backend()
    alternate = AlwaysIneligibleEligibilityBackend()

    # Default mock (EligibilityMock): Aetna member is eligible
    assert _check_eligible(default_mock, "Aetna", "AET123456789") is True

    # Alternate: same member appears not eligible (different backend)
    assert _check_eligible(alternate, "Aetna", "AET123456789") is False


# --- Config-driven backend selection ---


def test_get_integrations_config_default():
    """With no env vars, both backends default to 'mock'."""
    cfg = get_integrations_config()
    assert cfg["eligibility"] == "mock"
    assert cfg["prior_auth"] == "mock"


def test_get_integrations_config_from_env(monkeypatch):
    """ELIGIBILITY_BACKEND and PRIOR_AUTH_BACKEND are read from environment."""
    monkeypatch.setenv("ELIGIBILITY_BACKEND", "mock")
    monkeypatch.setenv("PRIOR_AUTH_BACKEND", "mock")
    cfg = get_integrations_config()
    assert cfg["eligibility"] == "mock"
    assert cfg["prior_auth"] == "mock"

    monkeypatch.setenv("ELIGIBILITY_BACKEND", "FHIR")
    cfg = get_integrations_config()
    assert cfg["eligibility"] == "fhir"


def test_registry_returns_mock_by_default():
    """Default (no env) yields EligibilityMock and PriorAuthMock."""
    reset_integration_backends()
    # Ensure no env override
    os.environ.pop("ELIGIBILITY_BACKEND", None)
    os.environ.pop("PRIOR_AUTH_BACKEND", None)
    elig = get_eligibility_backend()
    pa = get_prior_auth_backend()
    assert isinstance(elig, EligibilityMock)
    assert type(pa).__name__ == "PriorAuthMock"


def test_registry_explicit_mock_via_env(monkeypatch):
    """Explicit ELIGIBILITY_BACKEND=mock still yields EligibilityMock."""
    reset_integration_backends()
    monkeypatch.setenv("ELIGIBILITY_BACKEND", "mock")
    assert isinstance(get_eligibility_backend(), EligibilityMock)


def test_registry_unknown_eligibility_backend_raises(monkeypatch):
    """Unknown ELIGIBILITY_BACKEND raises ValueError with supported list."""
    reset_integration_backends()
    monkeypatch.setenv("ELIGIBILITY_BACKEND", "fhir")
    with pytest.raises(ValueError) as exc_info:
        get_eligibility_backend()
    assert "fhir" in str(exc_info.value)
    assert "mock" in str(exc_info.value).lower() or "Supported" in str(exc_info.value)


def test_registry_unknown_prior_auth_backend_raises(monkeypatch):
    """Unknown PRIOR_AUTH_BACKEND raises ValueError."""
    reset_integration_backends()
    monkeypatch.setenv("PRIOR_AUTH_BACKEND", "fhir")
    with pytest.raises(ValueError) as exc_info:
        get_prior_auth_backend()
    assert "fhir" in str(exc_info.value)
