"""Unit tests for router classification and route_encounter."""

import json
from pathlib import Path

import pytest

from rcm_agent.crews.main_crew import dispatch_to_crew, estimate_charges, process_encounter
from rcm_agent.crews.router import classify_encounter, route_encounter
from rcm_agent.models import Encounter, RcmStage


def _load_encounter(examples_dir: Path, filename: str) -> Encounter:
    path = examples_dir / filename
    with open(path, encoding="utf-8") as f:
        return Encounter.model_validate(json.load(f))


def test_router_enc_001_routine_visit(examples_dir: Path) -> None:
    """ENC-001 (routine office visit) -> CODING_CHARGE_CAPTURE."""
    encounter = _load_encounter(examples_dir, "encounter_001_routine_visit.json")
    result = classify_encounter(encounter)
    assert result.stage == RcmStage.CODING_CHARGE_CAPTURE
    assert result.confidence >= 0.9
    assert "coding" in result.reasoning.lower() or "charge" in result.reasoning.lower()


def test_router_enc_002_mri_auth(examples_dir: Path) -> None:
    """ENC-002 (MRI knee 73721) -> PRIOR_AUTHORIZATION (CPT in auth-required list)."""
    encounter = _load_encounter(examples_dir, "encounter_002_mri_with_auth.json")
    result = classify_encounter(encounter)
    assert result.stage == RcmStage.PRIOR_AUTHORIZATION
    assert "73721" in result.reasoning


def test_router_enc_003_inpatient_surgery(examples_dir: Path) -> None:
    """ENC-003 (inpatient hip replacement) -> CODING_CHARGE_CAPTURE (27130/99223 not in default auth list)."""
    encounter = _load_encounter(examples_dir, "encounter_003_inpatient_surgery.json")
    result = classify_encounter(encounter)
    assert result.stage == RcmStage.CODING_CHARGE_CAPTURE
    assert result.confidence >= 0.9


def test_router_enc_004_denial(examples_dir: Path) -> None:
    """ENC-004 (denial scenario with denial_info) -> DENIAL_APPEAL (structured denial_info)."""
    encounter = _load_encounter(examples_dir, "encounter_004_denial_scenario.json")
    result = classify_encounter(encounter)
    assert result.stage == RcmStage.DENIAL_APPEAL
    assert "denial" in result.reasoning.lower() or "appeal" in result.reasoning.lower() or "denial_info" in result.reasoning.lower()


def test_router_denial_info_routes_to_denial_appeal(examples_dir: Path) -> None:
    """Encounter with denial_info but no denial keywords in notes still routes to DENIAL_APPEAL."""
    from rcm_agent.models import DenialInfo
    encounter = _load_encounter(examples_dir, "encounter_001_routine_visit.json")
    encounter = encounter.model_copy(
        update={
            "clinical_notes": "Routine visit, no denial mentioned.",
            "denial_info": DenialInfo(claim_id="CLM-X", reason_codes=["PR-96"], denial_date="2026-01-01"),
        }
    )
    result = classify_encounter(encounter)
    assert result.stage == RcmStage.DENIAL_APPEAL
    assert "denial_info" in result.reasoning.lower()


def test_router_denial_info_empty_reason_codes_routes_to_denial_appeal(examples_dir: Path) -> None:
    """Encounter with denial_info and empty reason_codes (no denial keywords in notes) still routes to DENIAL_APPEAL."""
    from rcm_agent.models import DenialInfo
    encounter = _load_encounter(examples_dir, "encounter_001_routine_visit.json")
    encounter = encounter.model_copy(
        update={
            "clinical_notes": "Routine visit, no denial or appeal mentioned.",
            "denial_info": DenialInfo(claim_id="CLM-X", reason_codes=[], denial_date=None),
        }
    )
    result = classify_encounter(encounter)
    assert result.stage == RcmStage.DENIAL_APPEAL
    assert "denial_info" in result.reasoning.lower()


def test_router_enc_005_eligibility(examples_dir: Path) -> None:
    """ENC-005 (eligibility mismatch) -> ELIGIBILITY_VERIFICATION."""
    encounter = _load_encounter(examples_dir, "encounter_005_eligibility_mismatch.json")
    result = classify_encounter(encounter)
    assert result.stage == RcmStage.ELIGIBILITY_VERIFICATION
    assert result.confidence == 1.0


def test_route_encounter_returns_router_result(examples_dir: Path) -> None:
    """route_encounter returns RouterResult with stage, confidence, reasoning."""
    encounter = _load_encounter(examples_dir, "encounter_001_routine_visit.json")
    result = route_encounter(encounter)
    assert result.stage in RcmStage
    assert 0 <= result.confidence <= 1
    assert isinstance(result.reasoning, str) and len(result.reasoning) > 0


def test_process_encounter_enc_001_no_escalation(examples_dir: Path) -> None:
    """Process ENC-001: router -> coding, no escalation (low charges, complete data)."""
    encounter = _load_encounter(examples_dir, "encounter_001_routine_visit.json")
    output = process_encounter(encounter)
    assert output.encounter_id == "ENC-001"
    assert output.stage == RcmStage.CODING_CHARGE_CAPTURE
    assert output.stage != RcmStage.HUMAN_ESCALATION
    assert "router_confidence" in output.raw_result


def test_process_encounter_enc_003_high_value_escalation(
    examples_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ENC-003 (hip replacement) has high estimated charges -> escalation."""
    monkeypatch.setenv("ESCALATION_HIGH_VALUE_THRESHOLD", "5000")
    monkeypatch.setenv("ESCALATION_ONCOLOGY_FLAG", "false")
    encounter = _load_encounter(examples_dir, "encounter_003_inpatient_surgery.json")
    output = process_encounter(encounter)
    assert output.encounter_id == "ENC-003"
    assert output.stage == RcmStage.HUMAN_ESCALATION
    assert output.status.value == "NEEDS_REVIEW"
    assert "escalation_reasons" in output.raw_result
    assert any(
        "charges" in r.lower() and "5000" in r.replace(",", "")
        for r in output.raw_result.get("escalation_reasons", [])
    )


def test_process_encounter_enc_002_prior_auth(examples_dir: Path) -> None:
    """Process ENC-002: router -> prior auth, stub returns AUTH_APPROVED (no escalation)."""
    encounter = _load_encounter(examples_dir, "encounter_002_mri_with_auth.json")
    output = process_encounter(encounter)
    assert output.stage == RcmStage.PRIOR_AUTHORIZATION
    assert output.raw_result.get("router_stage") == "PRIOR_AUTHORIZATION"


def test_process_encounter_enc_004_denial_crew(examples_dir: Path) -> None:
    """Process ENC-004: router -> DENIAL_APPEAL -> denial/appeal crew returns analysis and artifacts."""
    encounter = _load_encounter(examples_dir, "encounter_004_denial_scenario.json")
    output = process_encounter(encounter)
    assert output.encounter_id == "ENC-004"
    assert output.stage == RcmStage.DENIAL_APPEAL
    assert output.status.value in ("NEEDS_REVIEW", "CLAIM_DENIED")
    assert output.raw_result.get("stub") is not True
    assert "reason_codes" in output.raw_result
    assert "denial_type" in output.raw_result


def test_dispatch_to_crew_eligibility(encounter_005: Encounter) -> None:
    """dispatch_to_crew with ELIGIBILITY_VERIFICATION runs eligibility crew."""
    output = dispatch_to_crew(encounter_005, RcmStage.ELIGIBILITY_VERIFICATION)
    assert output.stage == RcmStage.ELIGIBILITY_VERIFICATION
    assert output.encounter_id == encounter_005.encounter_id


def test_dispatch_to_crew_prior_auth(encounter_002: Encounter) -> None:
    """dispatch_to_crew with PRIOR_AUTHORIZATION runs prior auth crew."""
    output = dispatch_to_crew(encounter_002, RcmStage.PRIOR_AUTHORIZATION)
    assert output.stage == RcmStage.PRIOR_AUTHORIZATION
    assert "auth_id" in output.raw_result


def test_dispatch_to_crew_coding(encounter_001: Encounter) -> None:
    """dispatch_to_crew with CODING_CHARGE_CAPTURE runs coding crew."""
    output = dispatch_to_crew(encounter_001, RcmStage.CODING_CHARGE_CAPTURE)
    assert output.stage == RcmStage.CODING_CHARGE_CAPTURE
    assert "suggested_codes" in output.raw_result


def test_dispatch_to_crew_claims_submission_stub(encounter_001: Encounter) -> None:
    """dispatch_to_crew with CLAIMS_SUBMISSION uses stub."""
    output = dispatch_to_crew(encounter_001, RcmStage.CLAIMS_SUBMISSION)
    assert output.stage == RcmStage.CLAIMS_SUBMISSION
    assert output.raw_result.get("stub") is True


def test_dispatch_to_crew_denial_appeal_crew(encounter_004: Encounter) -> None:
    """dispatch_to_crew with DENIAL_APPEAL runs denial/appeal crew."""
    output = dispatch_to_crew(encounter_004, RcmStage.DENIAL_APPEAL)
    assert output.stage == RcmStage.DENIAL_APPEAL
    assert output.raw_result.get("stub") is not True
    assert "reason_codes" in output.raw_result
    assert "appeal_viable" in output.raw_result


def test_estimate_charges_known_cpt(encounter_002: Encounter) -> None:
    """estimate_charges returns known amount for 73721 (MRI knee)."""
    total = estimate_charges(encounter_002)
    assert total == 800.0


def test_estimate_charges_unknown_cpt(examples_dir: Path) -> None:
    """estimate_charges uses default for CPT not in map."""
    encounter = _load_encounter(examples_dir, "encounter_001_routine_visit.json")
    total = estimate_charges(encounter)
    assert total == 150.0  # 99213 is in map
    # Encounter with unknown code would get _DEFAULT_ESTIMATE (500.0)
    from rcm_agent.models import ProcedureCode
    enc_unknown = encounter.model_copy(
        update={"procedures": [ProcedureCode(code="99999", description="Unknown")]}
    )
    total_unknown = estimate_charges(enc_unknown)
    assert total_unknown == 500.0
