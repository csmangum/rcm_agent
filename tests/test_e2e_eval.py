"""Unit tests for e2e evaluation module (no LLM calls)."""

import json
from pathlib import Path
from unittest.mock import patch

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
    """Prior auth stage with AUTH_DENIED produces (True, False) (terminal decision)."""
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


def test_extract_prior_auth_from_outputs_pending() -> None:
    """Prior auth stage with non-terminal status (e.g. AUTH_REQUIRED) produces (False, None)."""
    out = EncounterOutput(
        encounter_id="ENC-X",
        stage=RcmStage.PRIOR_AUTHORIZATION,
        status=EncounterStatus.AUTH_REQUIRED,
        actions_taken=[],
        artifacts=[],
        message="Pending",
        raw_result={"authorization_number": "PENDING-1"},
    )
    produced, approved = _extract_prior_auth_from_outputs([out])
    assert produced is False
    assert approved is None


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
    golden_path.write_text('{"ENC-001": {"expected_stages": ["CODING_CHARGE_CAPTURE", "CLAIMS_SUBMISSION"]}}')
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


@patch("rcm_agent.crews.e2e_eval.process_encounter_multi_stage")
def test_run_e2e_evaluation_failure_status_success(
    mock_pipeline: object,
    encounter_005: Encounter,
    tmp_path: Path,
) -> None:
    """When golden expects NOT_ELIGIBLE, mock returning NOT_ELIGIBLE is success."""
    mock_pipeline.return_value = [
        EncounterOutput(
            encounter_id="ENC-005",
            stage=RcmStage.ELIGIBILITY_VERIFICATION,
            status=EncounterStatus.NOT_ELIGIBLE,
            actions_taken=[],
            artifacts=[],
            message="Not eligible",
            raw_result={},
        ),
    ]
    golden_path = tmp_path / "golden.json"
    golden_path.write_text(
        '{"ENC-005": {"expected_stages": ["ELIGIBILITY_VERIFICATION"], "expected_final_status": "NOT_ELIGIBLE"}}'
    )
    summary = run_e2e_evaluation(
        encounters=[encounter_005],
        golden_path=golden_path,
        pipeline_mode="multi",
    )
    assert summary.total == 1
    r = summary.records[0]
    assert r.final_status == "NOT_ELIGIBLE"
    assert r.success is True


@patch("rcm_agent.crews.e2e_eval.process_encounter_multi_stage")
def test_run_e2e_evaluation_escalation_success(
    mock_pipeline: object,
    encounter_003: Encounter,
    tmp_path: Path,
) -> None:
    """When golden expects escalation, mock returning HUMAN_ESCALATION + NEEDS_REVIEW is success."""
    mock_pipeline.return_value = [
        EncounterOutput(
            encounter_id="ENC-003",
            stage=RcmStage.HUMAN_ESCALATION,
            status=EncounterStatus.NEEDS_REVIEW,
            actions_taken=[],
            artifacts=[],
            message="Escalated",
            raw_result={},
        ),
    ]
    golden_path = tmp_path / "golden.json"
    golden_path.write_text(
        '{"ENC-003": {"expected_stages": ["HUMAN_ESCALATION"], "expected_final_status": "NEEDS_REVIEW", "expected_escalation": true}}'
    )
    summary = run_e2e_evaluation(
        encounters=[encounter_003],
        golden_path=golden_path,
        pipeline_mode="multi",
    )
    assert summary.total == 1
    r = summary.records[0]
    assert r.final_status == "NEEDS_REVIEW"
    assert r.escalated is True
    assert r.success is True


@patch("rcm_agent.crews.e2e_eval.process_encounter")
def test_run_e2e_evaluation_pipeline_mode_single(
    mock_single: object,
    encounter_001: Encounter,
    tmp_path: Path,
) -> None:
    """Pipeline mode single uses process_encounter; report has pipeline_mode single."""
    mock_single.return_value = EncounterOutput(
        encounter_id="ENC-001",
        stage=RcmStage.CODING_CHARGE_CAPTURE,
        status=EncounterStatus.CODED,
        actions_taken=[],
        artifacts=[],
        message="Coded",
        raw_result={},
    )
    golden_path = tmp_path / "golden.json"
    golden_path.write_text("{}")
    output_path = tmp_path / "e2e_single.json"
    summary = run_e2e_evaluation(
        encounters=[encounter_001],
        golden_path=golden_path,
        output_path=output_path,
        pipeline_mode="single",
    )
    assert isinstance(summary, E2ESummary)
    assert summary.pipeline_mode == "single"
    assert summary.total == 1
    assert output_path.exists()
    data = json.loads(output_path.read_text())
    assert data["pipeline_mode"] == "single"


@patch("rcm_agent.crews.e2e_eval.process_encounter_multi_stage")
@patch("rcm_agent.crews.e2e_eval.process_encounter")
def test_run_e2e_evaluation_pipeline_mode_both(
    mock_single: object,
    mock_multi: object,
    encounter_001: Encounter,
    tmp_path: Path,
) -> None:
    """Pipeline mode both writes e2e_eval_single.json and e2e_eval_multi.json with correct pipeline_mode."""
    out_single = EncounterOutput(
        encounter_id="ENC-001",
        stage=RcmStage.CODING_CHARGE_CAPTURE,
        status=EncounterStatus.CODED,
        actions_taken=[],
        artifacts=[],
        message="Coded",
        raw_result={},
    )
    mock_single.return_value = out_single
    mock_multi.return_value = [out_single]
    golden_path = tmp_path / "golden.json"
    golden_path.write_text("{}")
    result = run_e2e_evaluation(
        encounters=[encounter_001],
        golden_path=golden_path,
        output_dir=tmp_path,
        pipeline_mode="both",
    )
    assert isinstance(result, tuple)
    single_summary, multi_summary = result
    assert single_summary.pipeline_mode == "single"
    assert multi_summary.pipeline_mode == "multi"
    single_path = tmp_path / "e2e_eval_single.json"
    multi_path = tmp_path / "e2e_eval_multi.json"
    assert single_path.exists()
    assert multi_path.exists()
    assert json.loads(single_path.read_text())["pipeline_mode"] == "single"
    assert json.loads(multi_path.read_text())["pipeline_mode"] == "multi"


def test_run_e2e_evaluation_env_not_overridden(
    encounter_001: Encounter,
    tmp_path: Path,
) -> None:
    """When RCM_PRIOR_AUTH_MOCK_DENY_PAYER is already set, eval does not overwrite it."""
    import os

    with patch("rcm_agent.crews.e2e_eval.process_encounter_multi_stage") as mock_pipeline:
        mock_pipeline.return_value = [
            EncounterOutput(
                encounter_id="ENC-001",
                stage=RcmStage.CODING_CHARGE_CAPTURE,
                status=EncounterStatus.CODED,
                actions_taken=[],
                artifacts=[],
                message="Coded",
                raw_result={},
            ),
        ]
        key = "RCM_PRIOR_AUTH_MOCK_DENY_PAYER"
        os.environ[key] = "OtherPayer"
        try:
            run_e2e_evaluation(
                encounters=[encounter_001],
                golden_path=tmp_path / "golden.json",
                output_path=tmp_path / "out.json",
            )
            assert os.environ.get(key) == "OtherPayer"
        finally:
            os.environ.pop(key, None)


def test_run_e2e_evaluation_env_restored_when_set(
    encounter_001: Encounter,
    tmp_path: Path,
) -> None:
    """When key was not set, eval sets it for the run then restores (removes) afterward."""
    import os

    key = "RCM_PRIOR_AUTH_MOCK_DENY_PAYER"
    saved = os.environ.pop(key, None)
    try:
        with patch("rcm_agent.crews.e2e_eval.process_encounter_multi_stage") as mock_pipeline:
            mock_pipeline.return_value = [
                EncounterOutput(
                    encounter_id="ENC-001",
                    stage=RcmStage.CODING_CHARGE_CAPTURE,
                    status=EncounterStatus.CODED,
                    actions_taken=[],
                    artifacts=[],
                    message="Coded",
                    raw_result={},
                ),
            ]
            run_e2e_evaluation(
                encounters=[encounter_001],
                golden_path=tmp_path / "golden.json",
                output_path=tmp_path / "out.json",
            )
        assert key not in os.environ or os.environ.get(key, "").strip() == ""
    finally:
        if saved is not None:
            os.environ[key] = saved
        else:
            os.environ.pop(key, None)
