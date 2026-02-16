"""Unit tests for router classification and route_encounter."""

import json
from pathlib import Path

import pytest

from rcm_agent.crews.main_crew import process_encounter
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
    """ENC-004 (denial scenario) -> DENIAL_APPEAL."""
    encounter = _load_encounter(examples_dir, "encounter_004_denial_scenario.json")
    result = classify_encounter(encounter)
    assert result.stage == RcmStage.DENIAL_APPEAL
    assert "denial" in result.reasoning.lower() or "appeal" in result.reasoning.lower()


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
    assert any("charges" in r or "5000" in r for r in output.raw_result.get("escalation_reasons", []))


def test_process_encounter_enc_002_prior_auth(examples_dir: Path) -> None:
    """Process ENC-002: router -> prior auth, stub returns AUTH_APPROVED (no escalation)."""
    encounter = _load_encounter(examples_dir, "encounter_002_mri_with_auth.json")
    output = process_encounter(encounter)
    assert output.stage == RcmStage.PRIOR_AUTHORIZATION
    assert output.raw_result.get("router_stage") == "PRIOR_AUTHORIZATION"
