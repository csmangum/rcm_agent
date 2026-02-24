"""Integration tests for eligibility verification crew."""

from rcm_agent.crews.eligibility_crew import run_eligibility_crew
from rcm_agent.models import EncounterStatus, RcmStage


def test_eligibility_crew_enc_001_eligible(encounter_001):
    output = run_eligibility_crew(encounter_001)
    assert output.encounter_id == "ENC-001"
    assert output.stage == RcmStage.ELIGIBILITY_VERIFICATION
    assert output.status == EncounterStatus.ELIGIBLE
    assert "check_member_eligibility" in output.actions_taken
    assert "verify_benefits" in output.actions_taken
    assert output.raw_result.get("eligibility", {}).get("eligible") is True


def test_eligibility_crew_enc_005_not_eligible(encounter_005):
    output = run_eligibility_crew(encounter_005)
    assert output.encounter_id == "ENC-005"
    assert output.stage == RcmStage.ELIGIBILITY_VERIFICATION
    assert output.status == EncounterStatus.NOT_ELIGIBLE
    assert output.raw_result.get("eligibility", {}).get("eligible") is False
    assert "coverage_gaps" in output.raw_result


def test_eligibility_crew_eligible_with_gaps_returns_needs_review(encounter_001, monkeypatch):
    """When member is eligible but flag_coverage_gaps returns gaps, status is NEEDS_REVIEW."""

    def mock_flag_gaps(_eligibility_result):
        return ["Provider or facility may be out-of-network."]

    monkeypatch.setattr(
        "rcm_agent.crews.eligibility_crew.flag_coverage_gaps",
        mock_flag_gaps,
    )
    output = run_eligibility_crew(encounter_001)
    assert output.encounter_id == "ENC-001"
    assert output.stage == RcmStage.ELIGIBILITY_VERIFICATION
    assert output.status == EncounterStatus.NEEDS_REVIEW
    assert "hold" in output.message.lower() or "review" in output.message.lower()
    assert output.raw_result.get("coverage_gaps")


def test_eligibility_crew_unknown_payer_returns_sensible_output():
    """Eligibility crew with unknown payer/member_id completes (mock returns default eligible)."""
    from rcm_agent.models import DiagnosisCode, Encounter, EncounterType, Insurance, Patient, ProcedureCode

    encounter = Encounter(
        encounter_id="ENC-UNK",
        patient=Patient(age=30, gender="F", zip="10001"),
        insurance=Insurance(payer="UnknownPayer", member_id="UNK999", plan_type="PPO"),
        date="2026-02-10",
        type=EncounterType.office_visit,
        procedures=[ProcedureCode(code="99213", description="Office visit")],
        diagnoses=[DiagnosisCode(code="Z00.00", description="Encounter for checkup")],
        clinical_notes="Routine visit.",
        documents=[],
    )
    output = run_eligibility_crew(encounter)
    assert output.encounter_id == "ENC-UNK"
    assert output.stage == RcmStage.ELIGIBILITY_VERIFICATION
    assert "eligibility" in output.raw_result
