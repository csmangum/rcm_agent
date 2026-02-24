"""Integration tests for claims submission crew."""

from rcm_agent.crews.claims_submission_crew import run_claims_submission_crew
from rcm_agent.models import (
    DiagnosisCode,
    Encounter,
    EncounterStatus,
    EncounterType,
    Insurance,
    Patient,
    RcmStage,
)


def test_claims_crew_enc_001_accepted(encounter_001):
    output = run_claims_submission_crew(encounter_001)
    assert output.encounter_id == "ENC-001"
    assert output.stage == RcmStage.CLAIMS_SUBMISSION
    assert output.status == EncounterStatus.CLAIM_ACCEPTED
    assert "assemble_clean_claim" in output.actions_taken
    assert "scrub_claim" in output.actions_taken
    assert "submit_claim" in output.actions_taken
    assert "check_remit_status" in output.actions_taken
    assert output.raw_result.get("claim_id") is not None
    assert output.raw_result["claim_id"].startswith("CLM-")
    assert len(output.artifacts) == 2
    assert any("claim_837" in a for a in output.artifacts)
    assert any("remittance_835" in a for a in output.artifacts)


def test_claims_crew_enc_003_inpatient(encounter_003):
    output = run_claims_submission_crew(encounter_003)
    assert output.encounter_id == "ENC-003"
    assert output.stage == RcmStage.CLAIMS_SUBMISSION
    assert output.status == EncounterStatus.CLAIM_ACCEPTED
    claim_data = output.raw_result.get("claim_data", {})
    assert "27130" in claim_data.get("cpt_codes", [])
    assert "57" in claim_data.get("modifiers", [])
    remit = output.raw_result.get("remit_result", {})
    assert remit.get("paid_amount", 0) > 0


def test_claims_crew_with_coding_result(encounter_001):
    coding_result = {
        "icd_codes": [{"code": "J02.9", "description": "Pharyngitis", "confidence": 0.85}],
        "cpt_codes": [],
        "confidence": 0.85,
        "validation": {"valid": True, "invalid_pairs": [], "modifier_suggestions": []},
    }
    output = run_claims_submission_crew(encounter_001, coding_result=coding_result)
    assert output.status in (EncounterStatus.CLAIM_ACCEPTED, EncounterStatus.CLAIM_SUBMITTED)
    claim_data = output.raw_result.get("claim_data", {})
    assert "J02.9" in claim_data.get("icd_codes", [])


def test_claims_crew_with_authorization_number(encounter_001):
    output = run_claims_submission_crew(encounter_001, authorization_number="AUTH-ABCD1234")
    assert output.status in (EncounterStatus.CLAIM_ACCEPTED, EncounterStatus.CLAIM_SUBMITTED)
    claim_data = output.raw_result.get("claim_data", {})
    assert claim_data.get("authorization_number") == "AUTH-ABCD1234"


def test_claims_crew_scrub_failure_returns_needs_review(encounter_001, monkeypatch):
    """When scrub_claim returns errors, status is NEEDS_REVIEW."""

    def mock_scrub(_data):
        return {
            "clean": False,
            "errors": [{"field": "member_id", "code": "INVALID", "message": "Member ID not found."}],
            "warnings": [],
            "edit_actions": [],
        }

    monkeypatch.setattr(
        "rcm_agent.crews.claims_submission_crew.scrub_claim",
        mock_scrub,
    )
    output = run_claims_submission_crew(encounter_001)
    assert output.status == EncounterStatus.NEEDS_REVIEW
    assert "scrubbing" in output.message.lower() or "failed" in output.message.lower()


def test_claims_crew_paid_message_includes_amount(encounter_001):
    output = run_claims_submission_crew(encounter_001)
    assert "$" in output.message
    assert output.raw_result["remit_result"]["paid_amount"] > 0


def test_claims_crew_empty_procedures():
    """Claims crew with no procedures produces a scrub failure."""
    encounter = Encounter(
        encounter_id="ENC-NOPROC",
        patient=Patient(age=40, gender="M", zip="10001"),
        insurance=Insurance(payer="Aetna", member_id="AET123456789", plan_type="PPO"),
        date="2026-02-10",
        type=EncounterType.office_visit,
        procedures=[],
        diagnoses=[DiagnosisCode(code="J06.9", description="URI")],
        clinical_notes="No procedures.",
        documents=[],
    )
    output = run_claims_submission_crew(encounter)
    assert output.stage == RcmStage.CLAIMS_SUBMISSION
    assert output.status == EncounterStatus.NEEDS_REVIEW


def test_claims_crew_remit_has_adjustments(encounter_001):
    output = run_claims_submission_crew(encounter_001)
    remit = output.raw_result.get("remit_result", {})
    adjustments = remit.get("adjustments", [])
    assert len(adjustments) >= 1
    assert all("group_code" in a and "reason_code" in a for a in adjustments)


def test_claims_crew_stub_backend_graceful_handling(encounter_001, monkeypatch):
    """With stub backend (claim_id None), crew returns CLAIM_SUBMITTED and message has no 'None'."""
    from rcm_agent.integrations.claims_stub import ClaimsStub

    monkeypatch.setattr(
        "rcm_agent.tools.claims.get_claims_backend",
        lambda: ClaimsStub(),
    )
    output = run_claims_submission_crew(encounter_001)
    assert output.stage == RcmStage.CLAIMS_SUBMISSION
    assert output.status == EncounterStatus.CLAIM_SUBMITTED
    assert "None" not in output.message
    assert "stub" in output.message.lower()
    assert output.raw_result.get("claim_id") is None
