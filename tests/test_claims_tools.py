"""Unit tests for claims submission tools."""

from rcm_agent.models import (
    DiagnosisCode,
    Encounter,
    EncounterType,
    Insurance,
    Patient,
    ProcedureCode,
)
from rcm_agent.tools.claims import (
    assemble_clean_claim,
    check_remit_status,
    scrub_claim,
    submit_claim,
)


def _make_encounter(**overrides) -> Encounter:
    defaults = {
        "encounter_id": "ENC-CLM-TEST",
        "patient": Patient(age=45, gender="F", zip="10001"),
        "insurance": Insurance(payer="Aetna", member_id="AET123456789", plan_type="PPO"),
        "date": "2026-02-10",
        "type": EncounterType.office_visit,
        "procedures": [ProcedureCode(code="99213", description="Office visit, established patient")],
        "diagnoses": [DiagnosisCode(code="J06.9", description="Acute upper respiratory infection")],
        "clinical_notes": "URI, supportive care.",
        "documents": [],
    }
    defaults.update(overrides)
    return Encounter(**defaults)


# ---------------------------------------------------------------------------
# assemble_clean_claim
# ---------------------------------------------------------------------------


def test_assemble_clean_claim_basic():
    enc = _make_encounter()
    claim = assemble_clean_claim(enc)
    assert claim["encounter_id"] == "ENC-CLM-TEST"
    assert claim["payer"] == "Aetna"
    assert claim["member_id"] == "AET123456789"
    assert claim["icd_codes"] == ["J06.9"]
    assert claim["cpt_codes"] == ["99213"]
    assert claim["total_charges"] > 0
    assert len(claim["line_items"]) == 1
    assert claim["line_items"][0]["cpt_code"] == "99213"
    assert claim["place_of_service"] == "11"
    assert claim["authorization_number"] is None


def test_assemble_clean_claim_with_coding_result():
    enc = _make_encounter()
    coding_result = {
        "icd_codes": [{"code": "J02.9", "description": "Pharyngitis", "confidence": 0.85}],
        "cpt_codes": [],
        "validation": {"modifier_suggestions": []},
    }
    claim = assemble_clean_claim(enc, coding_result=coding_result)
    assert "J02.9" in claim["icd_codes"]
    assert "J06.9" in claim["icd_codes"]


def test_assemble_clean_claim_with_auth_number():
    enc = _make_encounter()
    claim = assemble_clean_claim(enc, authorization_number="AUTH-12345678")
    assert claim["authorization_number"] == "AUTH-12345678"


def test_assemble_clean_claim_inpatient_surgery():
    enc = _make_encounter(
        encounter_id="ENC-SURG",
        type=EncounterType.inpatient,
        procedures=[
            ProcedureCode(code="27130", description="Total hip arthroplasty"),
            ProcedureCode(code="99223", description="Initial hospital care"),
        ],
        diagnoses=[DiagnosisCode(code="M16.11", description="Osteoarthritis right hip")],
    )
    claim = assemble_clean_claim(enc)
    assert claim["place_of_service"] == "21"
    assert "27130" in claim["cpt_codes"]
    assert "99223" in claim["cpt_codes"]
    assert "57" in claim["modifiers"]
    assert claim["total_charges"] == 25450.00


def test_assemble_clean_claim_emergency():
    enc = _make_encounter(
        type=EncounterType.emergency,
        procedures=[ProcedureCode(code="99285", description="ED visit, high complexity")],
    )
    claim = assemble_clean_claim(enc)
    assert claim["place_of_service"] == "23"


# ---------------------------------------------------------------------------
# scrub_claim
# ---------------------------------------------------------------------------


def test_scrub_claim_clean():
    enc = _make_encounter()
    claim = assemble_clean_claim(enc)
    result = scrub_claim(claim)
    assert result["clean"] is True
    assert result["errors"] == []


def test_scrub_claim_missing_fields():
    result = scrub_claim({"encounter_id": "X", "payer": "P"})
    assert result["clean"] is False
    assert len(result["errors"]) >= 1
    missing_fields = {e["field"] for e in result["errors"]}
    assert "icd_codes" in missing_fields or "cpt_codes" in missing_fields


def test_scrub_claim_auto_modifier():
    enc = _make_encounter(
        type=EncounterType.inpatient,
        procedures=[
            ProcedureCode(code="27130", description="THA"),
            ProcedureCode(code="99223", description="Hospital care"),
        ],
    )
    claim = assemble_clean_claim(enc)
    claim_dict = dict(claim)
    claim_dict["modifiers"] = []
    result = scrub_claim(claim_dict)
    assert any("MOD57" in action for action in result["edit_actions"])


# ---------------------------------------------------------------------------
# submit_claim
# ---------------------------------------------------------------------------


def test_submit_claim():
    enc = _make_encounter()
    claim = assemble_clean_claim(enc)
    result = submit_claim(claim)
    assert result["claim_id"].startswith("CLM-")
    assert result["status"] == "accepted"
    assert "submitted_at" in result
    assert result["tracking_number"] is not None


# ---------------------------------------------------------------------------
# check_remit_status
# ---------------------------------------------------------------------------


def test_check_remit_status_after_submit():
    enc = _make_encounter()
    claim = assemble_clean_claim(enc)
    submit_result = submit_claim(claim)
    claim_id = submit_result["claim_id"]

    remit = check_remit_status(claim_id)
    assert remit["claim_id"] == claim_id
    assert remit["status"] == "paid"
    assert remit["paid_amount"] is not None
    assert remit["paid_amount"] > 0
    assert remit["allowed_amount"] is not None
    assert len(remit["adjustments"]) >= 1


def test_check_remit_status_unknown_claim():
    remit = check_remit_status("CLM-NONEXISTENT")
    assert remit["claim_id"] == "CLM-NONEXISTENT"
    assert remit["status"] == "not_found"
    assert remit["paid_amount"] is None
