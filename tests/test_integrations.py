"""Tests for integration protocols and stub implementations."""

import pytest

from rcm_agent.integrations import ClaimsBackend, ClaimsStub, EligibilityBackend


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
    from rcm_agent.tools.eligibility import check_member_eligibility

    # Wrap existing tool in a minimal adapter for this test only
    class ToolEligibilityAdapter:
        def check_member_eligibility(self, payer: str, member_id: str, date_of_service: str):
            return check_member_eligibility(payer, member_id, date_of_service)

        def verify_benefits(self, payer: str, member_id: str, procedure_codes: list):
            from rcm_agent.tools.eligibility import verify_benefits
            return verify_benefits(payer, member_id, procedure_codes)

    real_mock = ToolEligibilityAdapter()
    alternate = AlwaysIneligibleEligibilityBackend()

    # Real mock: Aetna member is eligible
    assert _check_eligible(real_mock, "Aetna", "AET123456789") is True

    # Alternate: same member appears not eligible (different backend)
    assert _check_eligible(alternate, "Aetna", "AET123456789") is False
