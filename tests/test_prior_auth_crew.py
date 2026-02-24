"""Integration tests for prior authorization crew."""

from rcm_agent.crews.prior_auth_crew import run_prior_auth_crew
from rcm_agent.models import EncounterStatus, RcmStage


def test_prior_auth_crew_enc_002_approved(encounter_002):
    output = run_prior_auth_crew(encounter_002)
    assert output.encounter_id == "ENC-002"
    assert output.stage == RcmStage.PRIOR_AUTHORIZATION
    assert output.status == EncounterStatus.AUTH_APPROVED
    assert "extract_clinical_indicators" in output.actions_taken
    assert "submit_auth_request" in output.actions_taken
    assert "poll_auth_status" in output.actions_taken
    assert output.raw_result.get("status_result", {}).get("decision") == "approved"
    assert len(output.artifacts) >= 1


def test_prior_auth_crew_no_procedures_completes():
    """Prior auth crew with no procedures still completes (empty procedure_codes in packet)."""
    from rcm_agent.models import DiagnosisCode, Encounter, EncounterType, Insurance, Patient

    encounter = Encounter(
        encounter_id="ENC-NOPROC",
        patient=Patient(age=50, gender="F", zip="10001"),
        insurance=Insurance(payer="Aetna", member_id="A1", plan_type="PPO"),
        date="2026-02-10",
        type=EncounterType.office_visit,
        procedures=[],
        diagnoses=[DiagnosisCode(code="Z00.00", description="Checkup")],
        clinical_notes="Consult only, no procedure.",
        documents=[],
    )
    output = run_prior_auth_crew(encounter)
    assert output.encounter_id == "ENC-NOPROC"
    assert output.stage == RcmStage.PRIOR_AUTHORIZATION
    assert output.raw_result.get("auth_packet", {}).get("procedure_codes") == []


def test_prior_auth_crew_uses_injected_policy_backend(encounter_002, monkeypatch):
    """When get_payer_policy_backend returns a callable, crew uses it for policy snippets."""
    custom_snippet = "Custom RAG policy snippet for 73721"
    monkeypatch.setattr(
        "rcm_agent.crews.prior_auth_crew.get_payer_policy_backend",
        lambda: lambda payer, code: [custom_snippet],
    )
    output = run_prior_auth_crew(encounter_002)
    assert output.stage == RcmStage.PRIOR_AUTHORIZATION
    policy_refs = output.raw_result.get("auth_packet", {}).get("policy_references", {})
    assert "73721" in policy_refs
    assert policy_refs["73721"] == [custom_snippet]
