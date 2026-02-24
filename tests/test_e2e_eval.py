"""Unit tests for e2e evaluation module (no LLM calls)."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from rcm_agent.crews.e2e_eval import (
    E2ERecord,
    E2ESummary,
    _compute_router_alignment,
    _encounter_needs_prior_auth,
    _extract_prior_auth_from_outputs,
    _load_golden,
    run_e2e_evaluation,
)
from rcm_agent.models import Encounter, EncounterOutput, EncounterStatus, RcmStage


def _load_encounter(examples_dir: Path, filename: str) -> Encounter:
    with open(examples_dir / filename, encoding="utf-8") as f:
        return Encounter.model_validate(json.load(f))


def test_encounter_needs_prior_auth_enc_002(examples_dir: Path) -> None:
    """ENC-002 has 73721 (MRI knee) which requires prior auth."""
    enc = _load_encounter(examples_dir, "encounter_002_mri_with_auth.json")
    assert _encounter_needs_prior_auth(enc) is True


def test_encounter_needs_prior_auth_enc_001(examples_dir: Path) -> None:
    """ENC-001 has 99213 (office visit) which does not require prior auth."""
    enc = _load_encounter(examples_dir, "encounter_001_routine_visit.json")
    assert _encounter_needs_prior_auth(enc) is False


def test_extract_prior_auth_from_outputs_approved() -> None:
    """Prior auth stage with AUTH_APPROVED produces (True, True)."""
    out = EncounterOutput(
        encounter_id="ENC-002",
        stage=RcmStage.PRIOR_AUTHORIZATION,
        status=EncounterStatus.AUTH_APPROVED,
        actions_taken=[],
        artifacts=[],
        message="Approved",
        raw_result={"authorization_number": "AUTH-123"},
    )
    produced, approved = _extract_prior_auth_from_outputs([out])
    assert produced is True
    assert approved is True


def test_extract_prior_auth_from_outputs_denied() -> None:
    """Prior auth stage with AUTH_DENIED produces (True, False)."""
    out = EncounterOutput(
        encounter_id="ENC-X",
        stage=RcmStage.PRIOR_AUTHORIZATION,
        status=EncounterStatus.AUTH_DENIED,
        actions_taken=[],
        artifacts=[],
        message="Denied",
        raw_result={},
    )
    produced, approved = _extract_prior_auth_from_outputs([out])
    assert produced is True
    assert approved is False


def test_extract_prior_auth_from_outputs_no_prior_auth_stage() -> None:
    """No prior auth stage produces (False, None)."""
    out = EncounterOutput(
        encounter_id="ENC-001",
        stage=RcmStage.CODING_CHARGE_CAPTURE,
        status=EncounterStatus.CODED,
        actions_taken=[],
        artifacts=[],
        message="Coded",
        raw_result={},
    )
    produced, approved = _extract_prior_auth_from_outputs([out])
    assert produced is False
    assert approved is None


def test_compute_router_alignment_aligned() -> None:
    """Stages match golden expected_stages -> True."""
    golden = {"expected_stages": ["CODING_CHARGE_CAPTURE", "CLAIMS_SUBMISSION"]}
    stages_run = ["CODING_CHARGE_CAPTURE", "CLAIMS_SUBMISSION"]
    assert _compute_router_alignment(stages_run, golden) is True


def test_compute_router_alignment_extra_stages_ok() -> None:
    """Extra stages (e.g. CLAIMS_SUBMISSION after coding) still aligned if expected subset."""
    golden = {"expected_stages": ["PRIOR_AUTHORIZATION", "CODING_CHARGE_CAPTURE"]}
    stages_run = ["PRIOR_AUTHORIZATION", "CODING_CHARGE_CAPTURE", "CLAIMS_SUBMISSION"]
    assert _compute_router_alignment(stages_run, golden) is True


def test_compute_router_alignment_missing_stage() -> None:
    """Missing expected stage -> False."""
    golden = {"expected_stages": ["PRIOR_AUTHORIZATION", "CODING_CHARGE_CAPTURE"]}
    stages_run = ["CODING_CHARGE_CAPTURE"]  # missing PRIOR_AUTHORIZATION
    assert _compute_router_alignment(stages_run, golden) is False


def test_compute_router_alignment_no_golden() -> None:
    """No golden data -> None."""
    assert _compute_router_alignment(["CODING_CHARGE_CAPTURE"], None) is None
    assert _compute_router_alignment(["CODING_CHARGE_CAPTURE"], {}) is None


def test_load_golden(tmp_path: Path) -> None:
    """Load golden.json from path."""
    golden_file = tmp_path / "golden.json"
    golden_file.write_text('{"ENC-001": {"expected_stages": ["CODING"]}}')
    result = _load_golden(golden_file)
    assert result == {"ENC-001": {"expected_stages": ["CODING"]}}


def test_load_golden_missing_returns_empty() -> None:
    """Missing file returns empty dict."""
    assert _load_golden(Path("/nonexistent/golden.json")) == {}


def test_e2e_eval_record_to_dict() -> None:
    """E2ERecord serializes to dict."""
    r = E2ERecord(
        encounter_id="ENC-001",
        stages_run=["CODING_CHARGE_CAPTURE", "CLAIMS_SUBMISSION"],
        final_status="CLAIM_SUBMITTED",
        escalated=False,
        prior_auth_needed=False,
        prior_auth_produced=False,
        prior_auth_approved=None,
        reached_claims=True,
        router_aligned=True,
        success=True,
    )
    d = r.to_dict()
    assert d["encounter_id"] == "ENC-001"
    assert d["stages_run"] == ["CODING_CHARGE_CAPTURE", "CLAIMS_SUBMISSION"]
    assert d["success"] is True


def test_e2e_eval_summary_rates() -> None:
    """E2ESummary computes rates correctly."""
    s = E2ESummary(total=4, pipeline_successes=3, prior_auth_needed_count=2)
    s.prior_auth_produced_count = 2
    s.reached_claims_count = 2
    s.golden_compared_count = 2
    s.router_aligned_count = 1
    assert s.pipeline_success_rate == 0.75
    assert s.prior_auth_coverage_rate == 1.0
    assert s.claim_readiness_rate == 0.5
    assert s.router_alignment_rate == 0.5


@patch("rcm_agent.crews.e2e_eval.process_encounter_multi_stage")
def test_run_e2e_evaluation_mocked(
    mock_pipeline: object,
    examples_dir: Path,
    encounter_001: Encounter,
    tmp_path: Path,
) -> None:
    """Run e2e eval with mocked pipeline (no LLM)."""
    mock_pipeline.return_value = [
        EncounterOutput(
            encounter_id="ENC-001",
            stage=RcmStage.CODING_CHARGE_CAPTURE,
            status=EncounterStatus.CODED,
            actions_taken=[],
            artifacts=[],
            message="Coded",
            raw_result={"suggested_codes": {"99213": "Office visit"}},
        ),
        EncounterOutput(
            encounter_id="ENC-001",
            stage=RcmStage.CLAIMS_SUBMISSION,
            status=EncounterStatus.CLAIM_SUBMITTED,
            actions_taken=[],
            artifacts=[],
            message="Submitted",
            raw_result={"claim_id": "CLM-001"},
        ),
    ]
    golden_path = tmp_path / "golden.json"
    golden_path.write_text(
        '{"ENC-001": {"expected_stages": ["CODING_CHARGE_CAPTURE", "CLAIMS_SUBMISSION"]}}'
    )
    output_path = tmp_path / "e2e_report.json"

    summary = run_e2e_evaluation(
        encounters=[encounter_001],
        golden_path=golden_path,
        output_path=output_path,
    )

    assert summary.total == 1
    assert len(summary.records) == 1
    r = summary.records[0]
    assert r.encounter_id == "ENC-001"
    assert r.stages_run == ["CODING_CHARGE_CAPTURE", "CLAIMS_SUBMISSION"]
    assert r.final_status == "CLAIM_SUBMITTED"
    assert r.reached_claims is True
    assert r.router_aligned is True
    assert r.success is True
    assert output_path.exists()
    assert (tmp_path / "e2e_report.md").exists()


@patch("rcm_agent.crews.e2e_eval.process_encounter_multi_stage")
def test_run_e2e_evaluation_pipeline_error(
    mock_pipeline: object,
    encounter_001: Encounter,
) -> None:
    """Pipeline exception produces ERROR record."""
    mock_pipeline.side_effect = RuntimeError("LLM timeout")
    summary = run_e2e_evaluation(encounters=[encounter_001])
    assert summary.total == 1
    r = summary.records[0]
    assert r.final_status == "ERROR"
    assert r.error == "LLM timeout"
    assert r.success is False
