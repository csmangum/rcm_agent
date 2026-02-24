"""Tests for intelligent routing: multi-stage, LLM-based, hybrid, config, and evaluation."""

import json
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from rcm_agent.config import get_cpt_charge_amounts, reload_routing_rules
from rcm_agent.config.settings import (
    _load_routing_rules,
    get_heuristic_keywords,
    get_multi_stage_sequences,
    get_payer_config,
    get_router_llm_config,
)
from rcm_agent.crews.main_crew import process_encounter_multi_stage
from rcm_agent.crews.router import (
    MultiStageRouterResult,
    RouterResult,
    _build_encounter_prompt,
    _parse_llm_response,
    classify_encounter,
    classify_encounter_multi_stage,
    llm_classify_encounter,
    route_encounter,
    route_encounter_multi_stage,
)
from rcm_agent.crews.router_eval import (
    EvalRecord,
    EvalSummary,
    evaluate_encounter,
    evaluate_encounters,
    load_encounters_from_dir,
    run_evaluation,
)
from rcm_agent.models import (
    DiagnosisCode,
    Encounter,
    EncounterOutput,
    EncounterStatus,
    EncounterType,
    Insurance,
    Patient,
    ProcedureCode,
    RcmStage,
)


def _load_encounter(examples_dir: Path, filename: str) -> Encounter:
    with open(examples_dir / filename, encoding="utf-8") as f:
        return Encounter.model_validate(json.load(f))


def _make_encounter(**overrides: Any) -> Encounter:
    """Build a minimal encounter with sensible defaults."""
    defaults: dict[str, Any] = {
        "encounter_id": "TEST-001",
        "patient": Patient(age=45, gender="F", zip="10001"),
        "insurance": Insurance(payer="Aetna", member_id="AET123", plan_type="PPO"),
        "date": "2026-02-10",
        "type": EncounterType.office_visit,
        "procedures": [ProcedureCode(code="99213", description="Office visit")],
        "diagnoses": [DiagnosisCode(code="J06.9", description="URI")],
        "clinical_notes": "Routine visit.",
        "documents": ["note.txt"],
    }
    defaults.update(overrides)
    return Encounter(**defaults)


# ---------------------------------------------------------------------------
# Multi-stage routing (heuristic)
# ---------------------------------------------------------------------------


class TestMultiStageRouting:
    def test_enc_002_mri_triggers_prior_auth_then_coding(self, examples_dir: Path) -> None:
        """MRI encounter -> PRIOR_AUTHORIZATION, then downstream CODING_CHARGE_CAPTURE."""
        enc = _load_encounter(examples_dir, "encounter_002_mri_with_auth.json")
        result = classify_encounter_multi_stage(enc)
        assert isinstance(result, MultiStageRouterResult)
        assert result.stages[0] == RcmStage.PRIOR_AUTHORIZATION
        assert RcmStage.CODING_CHARGE_CAPTURE in result.stages
        assert len(result.stages) >= 2

    def test_enc_005_eligibility_triggers_downstream(self, examples_dir: Path) -> None:
        """Eligibility encounter -> ELIGIBILITY_VERIFICATION, then checks downstream."""
        enc = _load_encounter(examples_dir, "encounter_005_eligibility_mismatch.json")
        result = classify_encounter_multi_stage(enc)
        assert result.stages[0] == RcmStage.ELIGIBILITY_VERIFICATION
        assert len(result.stages) >= 1

    def test_enc_001_routine_single_stage(self, examples_dir: Path) -> None:
        """Routine office visit -> only CODING_CHARGE_CAPTURE (no downstream)."""
        enc = _load_encounter(examples_dir, "encounter_001_routine_visit.json")
        result = classify_encounter_multi_stage(enc)
        assert result.stages[0] == RcmStage.CODING_CHARGE_CAPTURE
        downstream_seq = get_multi_stage_sequences().get("CODING_CHARGE_CAPTURE", [])
        if "CLAIMS_SUBMISSION" in downstream_seq:
            assert RcmStage.CLAIMS_SUBMISSION in result.stages

    def test_enc_004_denial_no_downstream(self, examples_dir: Path) -> None:
        """Denial encounters have no downstream stages defined."""
        enc = _load_encounter(examples_dir, "encounter_004_denial_scenario.json")
        result = classify_encounter_multi_stage(enc)
        assert result.stages[0] == RcmStage.DENIAL_APPEAL
        assert len(result.stages) == 1

    def test_multi_stage_result_properties(self) -> None:
        """MultiStageRouterResult.primary_stage and primary_confidence work."""
        result = MultiStageRouterResult(
            stages=[RcmStage.PRIOR_AUTHORIZATION, RcmStage.CODING_CHARGE_CAPTURE],
            results=[
                RouterResult(stage=RcmStage.PRIOR_AUTHORIZATION, confidence=1.0, reasoning="auth"),
                RouterResult(stage=RcmStage.CODING_CHARGE_CAPTURE, confidence=0.85, reasoning="coding"),
            ],
            reasoning="test",
        )
        assert result.primary_stage == RcmStage.PRIOR_AUTHORIZATION
        assert result.primary_confidence == 1.0

    def test_multi_stage_router_result_rejects_empty_stages(self) -> None:
        """MultiStageRouterResult raises ValidationError when stages/results are empty."""
        with pytest.raises(ValidationError) as exc_info:
            MultiStageRouterResult(
                stages=[],
                results=[],
                reasoning="",
            )
        assert "len(stages)" in str(exc_info.value) or "len(results)" in str(exc_info.value)

    def test_encounter_needing_eligibility_and_prior_auth(self) -> None:
        """Encounter with eligibility keywords AND auth-required CPT gets both stages."""
        enc = _make_encounter(
            encounter_id="MULTI-001",
            procedures=[ProcedureCode(code="73721", description="MRI knee")],
            clinical_notes="Insurance eligibility may have lapsed. MRI ordered.",
        )
        result = classify_encounter_multi_stage(enc)
        assert result.stages[0] == RcmStage.ELIGIBILITY_VERIFICATION
        assert RcmStage.PRIOR_AUTHORIZATION in result.stages
        assert RcmStage.CODING_CHARGE_CAPTURE in result.stages
        assert len(result.stages) >= 3


# ---------------------------------------------------------------------------
# Multi-stage pipeline execution
# ---------------------------------------------------------------------------


class TestMultiStagePipeline:
    def test_process_multi_stage_enc_002(self, examples_dir: Path) -> None:
        """Multi-stage pipeline for MRI encounter runs multiple stages."""
        enc = _load_encounter(examples_dir, "encounter_002_mri_with_auth.json")
        outputs = process_encounter_multi_stage(enc)
        assert len(outputs) >= 2
        assert outputs[0].stage == RcmStage.PRIOR_AUTHORIZATION
        assert outputs[-1].stage == RcmStage.CODING_CHARGE_CAPTURE
        assert outputs[0].raw_result["pipeline_position"] == 1
        assert outputs[-1].raw_result["pipeline_total_stages"] == len(outputs)

    def test_process_multi_stage_enc_001_single(self, examples_dir: Path) -> None:
        """Multi-stage pipeline for routine visit may include coding + claims."""
        enc = _load_encounter(examples_dir, "encounter_001_routine_visit.json")
        outputs = process_encounter_multi_stage(enc)
        assert len(outputs) >= 1
        assert outputs[0].stage == RcmStage.CODING_CHARGE_CAPTURE

    def test_process_multi_stage_enc_004_denial(self, examples_dir: Path) -> None:
        """Multi-stage pipeline for denial runs single denial stage."""
        enc = _load_encounter(examples_dir, "encounter_004_denial_scenario.json")
        outputs = process_encounter_multi_stage(enc)
        assert len(outputs) == 1
        assert outputs[0].stage == RcmStage.DENIAL_APPEAL

    def test_process_multi_stage_high_value_escalation(
        self, examples_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Multi-stage pipeline escalates on high-value encounters."""
        monkeypatch.setenv("ESCALATION_HIGH_VALUE_THRESHOLD", "5000")
        monkeypatch.setenv("ESCALATION_ONCOLOGY_FLAG", "false")
        enc = _load_encounter(examples_dir, "encounter_003_inpatient_surgery.json")
        outputs = process_encounter_multi_stage(enc)
        assert len(outputs) == 1
        assert outputs[0].stage == RcmStage.HUMAN_ESCALATION
        assert "router_stages" in outputs[0].raw_result

    def test_process_multi_stage_halts_on_not_eligible(self, examples_dir: Path) -> None:
        """When first stage returns NOT_ELIGIBLE, pipeline returns single output and does not run later stages."""
        enc = _load_encounter(examples_dir, "encounter_005_eligibility_mismatch.json")
        not_eligible_output = EncounterOutput(
            encounter_id=enc.encounter_id,
            stage=RcmStage.ELIGIBILITY_VERIFICATION,
            status=EncounterStatus.NOT_ELIGIBLE,
            actions_taken=["check_member_eligibility"],
            artifacts=[],
            message="Eligibility check: coverage lapsed or terminated.",
            raw_result={"eligibility": {"eligible": False}},
        )

        with patch("rcm_agent.crews.main_crew.dispatch_to_crew") as mock_dispatch:
            mock_dispatch.return_value = not_eligible_output
            outputs = process_encounter_multi_stage(enc)

        assert len(outputs) == 1
        assert outputs[0].status == EncounterStatus.NOT_ELIGIBLE
        assert outputs[0].stage == RcmStage.ELIGIBILITY_VERIFICATION
        mock_dispatch.assert_called_once()


# ---------------------------------------------------------------------------
# LLM router (mocked)
# ---------------------------------------------------------------------------


class TestLLMRouter:
    def _mock_completion(self, stages: list[dict[str, Any]]) -> MagicMock:
        """Build a mock litellm.completion response."""
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock()]
        mock_resp.choices[0].message.content = json.dumps({"stages": stages})
        return mock_resp

    def test_llm_classify_parses_single_stage(self, encounter_001: Encounter) -> None:
        mock_resp = self._mock_completion(
            [{"stage": "CODING_CHARGE_CAPTURE", "confidence": 0.95, "reasoning": "standard coding"}]
        )
        with patch("litellm.completion", return_value=mock_resp):
            result = llm_classify_encounter(encounter_001)
        assert result is not None
        assert result.primary_stage == RcmStage.CODING_CHARGE_CAPTURE
        assert result.primary_confidence == 0.95

    def test_llm_classify_parses_multi_stage(self, encounter_002: Encounter) -> None:
        mock_resp = self._mock_completion(
            [
                {"stage": "PRIOR_AUTHORIZATION", "confidence": 0.98, "reasoning": "MRI needs auth"},
                {"stage": "CODING_CHARGE_CAPTURE", "confidence": 0.90, "reasoning": "then coding"},
            ]
        )
        with patch("litellm.completion", return_value=mock_resp):
            result = llm_classify_encounter(encounter_002)
        assert result is not None
        assert len(result.stages) == 2
        assert result.stages[0] == RcmStage.PRIOR_AUTHORIZATION
        assert result.stages[1] == RcmStage.CODING_CHARGE_CAPTURE

    def test_llm_classify_returns_none_on_error(self, encounter_001: Encounter) -> None:
        with patch("litellm.completion", side_effect=Exception("API error")):
            result = llm_classify_encounter(encounter_001)
        assert result is None

    def test_llm_classify_filters_invalid_stages(self, encounter_001: Encounter) -> None:
        mock_resp = self._mock_completion(
            [
                {"stage": "INVALID_STAGE", "confidence": 0.9, "reasoning": "bad"},
                {"stage": "CODING_CHARGE_CAPTURE", "confidence": 0.85, "reasoning": "good"},
            ]
        )
        with patch("litellm.completion", return_value=mock_resp):
            result = llm_classify_encounter(encounter_001)
        assert result is not None
        assert len(result.stages) == 1
        assert result.stages[0] == RcmStage.CODING_CHARGE_CAPTURE

    def test_llm_classify_filters_intake_and_escalation(self, encounter_001: Encounter) -> None:
        mock_resp = self._mock_completion(
            [
                {"stage": "INTAKE", "confidence": 0.9, "reasoning": "intake"},
                {"stage": "HUMAN_ESCALATION", "confidence": 0.8, "reasoning": "escalate"},
                {"stage": "CODING_CHARGE_CAPTURE", "confidence": 0.85, "reasoning": "coding"},
            ]
        )
        with patch("litellm.completion", return_value=mock_resp):
            result = llm_classify_encounter(encounter_001)
        assert result is not None
        assert len(result.stages) == 1
        assert result.stages[0] == RcmStage.CODING_CHARGE_CAPTURE

    def test_llm_classify_returns_none_on_empty_response(self, encounter_001: Encounter) -> None:
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock()]
        mock_resp.choices[0].message.content = ""
        with patch("litellm.completion", return_value=mock_resp):
            result = llm_classify_encounter(encounter_001)
        assert result is None


class TestParseResponse:
    def test_parse_valid_json(self) -> None:
        text = json.dumps({"stages": [{"stage": "CODING_CHARGE_CAPTURE", "confidence": 0.9, "reasoning": "ok"}]})
        result = _parse_llm_response(text)
        assert len(result) == 1
        assert result[0]["stage"] == "CODING_CHARGE_CAPTURE"

    def test_parse_markdown_wrapped_json(self) -> None:
        text = '```json\n{"stages": [{"stage": "ELIGIBILITY_VERIFICATION", "confidence": 0.8}]}\n```'
        result = _parse_llm_response(text)
        assert len(result) == 1

    def test_parse_invalid_json(self) -> None:
        result = _parse_llm_response("not json at all")
        assert result == []

    def test_parse_missing_stages_key(self) -> None:
        result = _parse_llm_response('{"result": "something"}')
        assert result == []


class TestBuildPrompt:
    def test_prompt_contains_encounter_data(self, encounter_002: Encounter) -> None:
        prompt = _build_encounter_prompt(encounter_002)
        assert "ENC-002" in prompt
        assert "73721" in prompt
        assert "UnitedHealthcare" in prompt
        assert "MRI" in prompt

    def test_prompt_with_denial_info(self, encounter_004: Encounter) -> None:
        prompt = _build_encounter_prompt(encounter_004)
        assert "CLM-004" in prompt
        assert "CO-4" in prompt


# ---------------------------------------------------------------------------
# Hybrid routing
# ---------------------------------------------------------------------------


class TestHybridRouting:
    def test_route_encounter_uses_heuristic_when_confident(self, encounter_001: Encounter) -> None:
        """High-confidence heuristic skips LLM even if enabled."""
        result = route_encounter(encounter_001)
        assert result.stage == RcmStage.CODING_CHARGE_CAPTURE
        assert result.confidence >= 0.9

    def test_route_encounter_calls_llm_on_low_confidence(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When heuristic confidence is low and LLM is enabled, use LLM result."""
        monkeypatch.setenv("RCM_ROUTER_LLM_ENABLED", "true")
        enc = _make_encounter(
            procedures=[],
            diagnoses=[],
            clinical_notes="Unclear encounter.",
        )
        heuristic = classify_encounter(enc)
        assert heuristic.confidence < 0.9

        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock()]
        mock_resp.choices[0].message.content = json.dumps(
            {"stages": [{"stage": "ELIGIBILITY_VERIFICATION", "confidence": 0.92, "reasoning": "LLM says elig"}]}
        )
        with patch("litellm.completion", return_value=mock_resp):
            result = route_encounter(enc)
        assert result.stage == RcmStage.ELIGIBILITY_VERIFICATION
        assert result.confidence == 0.92

    def test_route_encounter_keeps_heuristic_when_llm_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When LLM fails, keep heuristic result."""
        monkeypatch.setenv("RCM_ROUTER_LLM_ENABLED", "true")
        enc = _make_encounter(procedures=[], diagnoses=[], clinical_notes="Unclear.")
        with patch("litellm.completion", side_effect=Exception("API error")):
            result = route_encounter(enc)
        assert result.stage == RcmStage.CODING_CHARGE_CAPTURE
        assert result.confidence == 0.7

    def test_route_encounter_multi_stage_with_llm_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Multi-stage route_encounter_multi_stage falls back to LLM on low confidence."""
        monkeypatch.setenv("RCM_ROUTER_LLM_ENABLED", "true")
        enc = _make_encounter(procedures=[], diagnoses=[], clinical_notes="Unclear.")

        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock()]
        mock_resp.choices[0].message.content = json.dumps(
            {
                "stages": [
                    {"stage": "ELIGIBILITY_VERIFICATION", "confidence": 0.9, "reasoning": "check elig"},
                    {"stage": "CODING_CHARGE_CAPTURE", "confidence": 0.8, "reasoning": "then code"},
                ]
            }
        )
        with patch("litellm.completion", return_value=mock_resp):
            result = route_encounter_multi_stage(enc)
        assert result.stages[0] == RcmStage.ELIGIBILITY_VERIFICATION
        assert len(result.stages) == 2


# ---------------------------------------------------------------------------
# Externalized config
# ---------------------------------------------------------------------------


class TestExternalizedConfig:
    def test_routing_rules_yaml_loaded(self) -> None:
        rules = reload_routing_rules()
        assert "auth_required_cpt" in rules
        assert "payer_rules" in rules
        assert "multi_stage_sequences" in rules
        assert "heuristic_keywords" in rules

    def test_payer_config_from_yaml(self) -> None:
        config = get_payer_config()
        assert "UnitedHealthcare" in config
        assert "Aetna" in config
        assert "common_denial_codes" in config["UnitedHealthcare"]

    def test_heuristic_keywords(self) -> None:
        kw = get_heuristic_keywords()
        assert "denial_appeal" in kw
        assert "eligibility" in kw
        assert "denial" in kw["denial_appeal"]

    def test_multi_stage_sequences(self) -> None:
        seqs = get_multi_stage_sequences()
        assert "ELIGIBILITY_VERIFICATION" in seqs
        assert "PRIOR_AUTHORIZATION" in seqs["ELIGIBILITY_VERIFICATION"]

    def test_router_llm_config(self) -> None:
        cfg = get_router_llm_config()
        assert "confidence_threshold" in cfg
        assert "model" in cfg
        assert isinstance(cfg["confidence_threshold"], (int, float))

    def test_config_reload_picks_up_yaml_changes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """After reload_routing_rules() with different YAML content, getters return updated values."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write('cpt_charge_amounts:\n  "99213": 999.0\n  "73721": 1.0\n')
            custom_path = Path(f.name)
        try:
            monkeypatch.setattr("rcm_agent.config.settings._ROUTING_RULES_PATH", custom_path)
            _load_routing_rules.cache_clear()
            reload_routing_rules()
            amounts = get_cpt_charge_amounts()
            assert amounts.get("99213") == 999.0
            assert amounts.get("73721") == 1.0
        finally:
            custom_path.unlink(missing_ok=True)
            _load_routing_rules.cache_clear()
            monkeypatch.undo()
            _load_routing_rules.cache_clear()


# ---------------------------------------------------------------------------
# Router evaluation
# ---------------------------------------------------------------------------


class TestRouterEvaluation:
    def test_evaluate_encounter_without_llm(self, encounter_001: Encounter, monkeypatch: pytest.MonkeyPatch) -> None:
        """Without LLM, evaluation records LLM as unavailable."""
        monkeypatch.setenv("RCM_ROUTER_LLM_ENABLED", "false")
        record = evaluate_encounter(encounter_001)
        assert isinstance(record, EvalRecord)
        assert record.encounter_id == "ENC-001"
        assert record.heuristic_stage == "CODING_CHARGE_CAPTURE"
        assert record.llm_stage is None
        assert not record.agrees
        assert "unavailable" in record.notes.lower() or "failed" in record.notes.lower()

    def test_evaluate_encounter_with_llm_agreement(
        self, encounter_001: Encounter, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When LLM agrees with heuristic, agrees=True."""
        monkeypatch.setenv("RCM_ROUTER_LLM_ENABLED", "true")
        with patch("rcm_agent.crews.router_eval.llm_classify_encounter") as mock_llm:
            mock_llm.return_value = MultiStageRouterResult(
                stages=[RcmStage.CODING_CHARGE_CAPTURE],
                results=[RouterResult(stage=RcmStage.CODING_CHARGE_CAPTURE, confidence=0.95, reasoning="coding")],
                reasoning="coding",
            )
            record = evaluate_encounter(encounter_001)
        assert record.agrees
        assert record.llm_stage == "CODING_CHARGE_CAPTURE"

    def test_evaluate_encounter_with_llm_disagreement(
        self, encounter_001: Encounter, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When LLM disagrees with heuristic, notes contain DISAGREEMENT."""
        monkeypatch.setenv("RCM_ROUTER_LLM_ENABLED", "true")
        with patch("rcm_agent.crews.router_eval.llm_classify_encounter") as mock_llm:
            mock_llm.return_value = MultiStageRouterResult(
                stages=[RcmStage.ELIGIBILITY_VERIFICATION],
                results=[RouterResult(stage=RcmStage.ELIGIBILITY_VERIFICATION, confidence=0.88, reasoning="elig")],
                reasoning="elig",
            )
            record = evaluate_encounter(encounter_001)
        assert not record.agrees
        assert "DISAGREEMENT" in record.notes

    def test_evaluate_encounters_summary(self, examples_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """evaluate_encounters returns proper summary stats."""
        monkeypatch.setenv("RCM_ROUTER_LLM_ENABLED", "false")
        encounters = load_encounters_from_dir(examples_dir)
        assert len(encounters) >= 5
        summary = evaluate_encounters(encounters)
        assert summary.total == len(encounters)
        assert summary.llm_failures == len(encounters)
        assert summary.agreement_rate == 0.0

    def test_eval_record_to_dict(self) -> None:
        record = EvalRecord(
            encounter_id="TEST",
            heuristic_stage="CODING_CHARGE_CAPTURE",
            heuristic_confidence=0.95,
            heuristic_reasoning="test",
            heuristic_stages_multi=["CODING_CHARGE_CAPTURE"],
            llm_stage="CODING_CHARGE_CAPTURE",
            llm_confidence=0.9,
            llm_reasoning="test",
            llm_stages_multi=["CODING_CHARGE_CAPTURE"],
            agrees=True,
            agrees_multi=True,
        )
        d = record.to_dict()
        assert d["encounter_id"] == "TEST"
        assert d["agrees"] is True

    def test_eval_summary_agreement_rate(self) -> None:
        summary = EvalSummary(total=10, agreements=7, disagreements=3, llm_failures=0)
        assert summary.agreement_rate == 0.7

    def test_eval_summary_with_llm_failures(self) -> None:
        summary = EvalSummary(total=10, agreements=5, disagreements=2, llm_failures=3)
        assert summary.agreement_rate == pytest.approx(5 / 7, abs=0.01)

    def test_load_encounters_from_dir(self, examples_dir: Path) -> None:
        encounters = load_encounters_from_dir(examples_dir)
        assert len(encounters) >= 5
        ids = {e.encounter_id for e in encounters}
        assert "ENC-001" in ids
        assert "ENC-002" in ids

    def test_run_evaluation_writes_report(
        self, examples_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("RCM_ROUTER_LLM_ENABLED", "false")
        output_path = tmp_path / "eval_report.json"
        summary = run_evaluation(examples_dir=examples_dir, output_path=output_path)
        assert output_path.exists()
        with open(output_path) as f:
            report = json.load(f)
        assert report["total"] == summary.total
        assert len(report["records"]) == summary.total
