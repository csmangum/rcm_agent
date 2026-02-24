"""Unit tests for claims backend implementations (mock, stub, HTTP client)."""

from rcm_agent.integrations.claims_mock import ClaimsMock
from rcm_agent.integrations.claims_stub import ClaimsStub
from rcm_agent.integrations.protocols import ClaimsBackend


def test_claims_mock_satisfies_protocol():
    assert isinstance(ClaimsMock(), ClaimsBackend)


def test_claims_stub_satisfies_protocol():
    assert isinstance(ClaimsStub(), ClaimsBackend)


# ---------------------------------------------------------------------------
# ClaimsMock
# ---------------------------------------------------------------------------


def test_claims_mock_scrub_clean():
    mock = ClaimsMock()
    payload = {
        "encounter_id": "ENC-1",
        "payer": "Aetna",
        "member_id": "AET123456789",
        "billing_provider_npi": "1234567890",
        "date_of_service": "2026-02-10",
        "icd_codes": ["J06.9"],
        "cpt_codes": ["99213"],
        "total_charges": 150.00,
    }
    result = mock.scrub_claim(payload)
    assert result["clean"] is True
    assert result["errors"] == []


def test_claims_mock_scrub_missing_fields():
    mock = ClaimsMock()
    result = mock.scrub_claim({})
    assert result["clean"] is False
    assert len(result["errors"]) >= 1


def test_claims_mock_scrub_anthem_member_id():
    mock = ClaimsMock()
    payload = {
        "encounter_id": "ENC-1",
        "payer": "Anthem",
        "member_id": "SHORT",
        "billing_provider_npi": "1234567890",
        "date_of_service": "2026-02-10",
        "icd_codes": ["R10.9"],
        "cpt_codes": ["99285"],
        "total_charges": 650.00,
    }
    result = mock.scrub_claim(payload)
    assert result["clean"] is False
    assert any(e["code"] == "ANT-001" for e in result["errors"])


def test_claims_mock_scrub_auto_modifier():
    mock = ClaimsMock()
    payload = {
        "encounter_id": "ENC-1",
        "payer": "BCBS",
        "member_id": "BCBS555111222",
        "billing_provider_npi": "1234567890",
        "date_of_service": "2026-02-10",
        "icd_codes": ["M16.11"],
        "cpt_codes": ["27130", "99223"],
        "total_charges": 25450.00,
    }
    result = mock.scrub_claim(payload)
    assert any("MOD57" in action for action in result["edit_actions"])


def test_claims_mock_submit():
    mock = ClaimsMock()
    payload = {"encounter_id": "ENC-1", "cpt_codes": ["99213"], "total_charges": 150}
    result = mock.submit_claim(payload)
    assert result["claim_id"].startswith("CLM-")
    assert result["status"] == "accepted"
    assert result["tracking_number"].startswith("TRK-")


def test_claims_mock_get_remit_after_submit():
    mock = ClaimsMock()
    payload = {"encounter_id": "ENC-1", "cpt_codes": ["99213"], "total_charges": 150}
    submit = mock.submit_claim(payload)
    remit = mock.get_remit(submit["claim_id"])
    assert remit["status"] == "paid"
    assert remit["paid_amount"] > 0
    assert remit["allowed_amount"] > 0
    assert remit["check_number"] is not None


def test_claims_mock_get_remit_not_found():
    mock = ClaimsMock()
    remit = mock.get_remit("CLM-NONEXISTENT")
    assert remit["status"] == "not_found"
    assert remit["paid_amount"] is None


def test_claims_mock_reset():
    mock = ClaimsMock()
    payload = {"encounter_id": "ENC-1", "cpt_codes": ["99213"], "total_charges": 150}
    submit = mock.submit_claim(payload)
    mock.reset()
    remit = mock.get_remit(submit["claim_id"])
    assert remit["status"] == "not_found"


# ---------------------------------------------------------------------------
# ClaimsStub
# ---------------------------------------------------------------------------


def test_claims_stub_submit():
    stub = ClaimsStub()
    result = stub.submit_claim({"encounter_id": "ENC-1"})
    assert result["stub"] is True
    assert result["claim_id"] is None
    assert result["status"] == "stub"


def test_claims_stub_get_remit():
    stub = ClaimsStub()
    result = stub.get_remit("CLM-999")
    assert result["stub"] is True
    assert result["claim_id"] == "CLM-999"
    assert result["payment"] is None
