"""Integration tests for coding and charge capture crew."""

from rcm_agent.crews.coding_crew import run_coding_crew
from rcm_agent.models import EncounterStatus, RcmStage


def test_coding_crew_enc_001_coded(encounter_001):
    output = run_coding_crew(encounter_001)
    assert output.encounter_id == "ENC-001"
    assert output.stage == RcmStage.CODING_CHARGE_CAPTURE
    assert output.status == EncounterStatus.CODED
    assert "suggest_codes" in output.actions_taken
    assert "validate_code_combinations" in output.actions_taken
    assert "calculate_expected_reimbursement" in output.actions_taken
    assert "suggested_codes" in output.raw_result
    assert "reimbursement" in output.raw_result
    assert "confidence" in output.raw_result


def test_coding_crew_empty_notes_completes_with_fallback():
    """Coding crew with empty clinical notes completes (uses existing codes, low confidence)."""
    from rcm_agent.models import DiagnosisCode, Encounter, EncounterType, Insurance, Patient, ProcedureCode

    encounter = Encounter(
        encounter_id="ENC-EMPTY",
        patient=Patient(age=40, gender="M", zip="10001"),
        insurance=Insurance(payer="Aetna", member_id="A1", plan_type="PPO"),
        date="2026-02-10",
        type=EncounterType.office_visit,
        procedures=[ProcedureCode(code="99213", description="Office visit")],
        diagnoses=[DiagnosisCode(code="J06.9", description="URI")],
        clinical_notes="",
        documents=[],
    )
    output = run_coding_crew(encounter)
    assert output.encounter_id == "ENC-EMPTY"
    assert output.stage == RcmStage.CODING_CHARGE_CAPTURE
    assert output.raw_result.get("confidence", 0) <= 0.6
    assert "suggested_codes" in output.raw_result


def test_coding_crew_validation_failure_returns_needs_review(encounter_001, monkeypatch):
    """When validate_code_combinations returns invalid pairs, status is NEEDS_REVIEW."""

    def mock_validate(_icd, _cpt):
        return {
            "valid": False,
            "invalid_pairs": [{"cpt_1": "99213", "cpt_2": "99214", "reason": "NCCI bundle"}],
            "modifier_suggestions": [],
        }

    monkeypatch.setattr(
        "rcm_agent.crews.coding_crew.validate_code_combinations",
        mock_validate,
    )
    output = run_coding_crew(encounter_001)
    assert output.status == EncounterStatus.NEEDS_REVIEW
    assert "review" in output.message.lower()


def test_coding_crew_enc_003_inpatient_surgery(encounter_003):
    """ENC-003: hip replacement (27130, 99223) exercises modifier-57 suggestion and reimbursement."""
    output = run_coding_crew(encounter_003)
    assert output.encounter_id == "ENC-003"
    assert output.stage == RcmStage.CODING_CHARGE_CAPTURE
    assert output.status == EncounterStatus.NEEDS_REVIEW  # missing_charge_flags (e.g. modifier 57)
    assert "suggest_codes" in output.actions_taken
    assert "validate_code_combinations" in output.actions_taken
    assert "27130" in str(output.raw_result.get("reimbursement", {}).get("per_code", []))
    # May have modifier suggestion for 27130+99223
    assert "validation" in output.raw_result


def test_coding_crew_includes_guidelines_snippets(encounter_001):
    """Coding crew calls search_coding_guidelines and includes snippets in raw_result."""
    output = run_coding_crew(encounter_001)
    assert "search_coding_guidelines" in output.actions_taken
    assert "coding_guidelines_snippets" in output.raw_result
    assert isinstance(output.raw_result["coding_guidelines_snippets"], list)


def test_coding_crew_uses_injected_guidelines_backend(encounter_001, monkeypatch):
    """When get_coding_guidelines_backend returns a callable, crew uses it."""
    custom_snippet = "Custom RAG coding guideline"
    monkeypatch.setattr(
        "rcm_agent.crews.coding_crew.get_coding_guidelines_backend",
        lambda: lambda query: [custom_snippet],
    )
    output = run_coding_crew(encounter_001)
    assert output.raw_result["coding_guidelines_snippets"] == [custom_snippet]
