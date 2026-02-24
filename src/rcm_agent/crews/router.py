"""Encounter router: heuristic, LLM-based, and multi-stage classification into RcmStage."""

from __future__ import annotations

import json
import os
from typing import Any

from pydantic import BaseModel, model_validator

from rcm_agent.config import (
    get_auth_required_procedures,
    get_heuristic_keywords,
    get_multi_stage_sequences,
    get_router_llm_config,
)
from rcm_agent.models import Encounter, RcmStage
from rcm_agent.observability.logging import get_logger

logger = get_logger(__name__)


class RouterResult(BaseModel):
    """Result of routing an encounter to an RCM stage."""

    stage: RcmStage
    confidence: float
    reasoning: str


class MultiStageRouterResult(BaseModel):
    """Result of multi-stage routing: ordered list of stages an encounter needs."""

    stages: list[RcmStage]
    results: list[RouterResult]
    reasoning: str

    @model_validator(mode="after")
    def _stages_and_results_non_empty_and_equal_length(self) -> MultiStageRouterResult:
        if len(self.stages) != len(self.results) or len(self.stages) == 0:
            raise ValueError(
                "MultiStageRouterResult requires len(stages) == len(results) > 0, "
                f"got stages={len(self.stages)}, results={len(self.results)}"
            )
        return self

    @property
    def primary_stage(self) -> RcmStage:
        return self.stages[0]

    @property
    def primary_confidence(self) -> float:
        return self.results[0].confidence


def _llm_router_enabled() -> bool:
    """True if LLM-based router fallback is enabled (default: false)."""
    raw = os.environ.get("RCM_ROUTER_LLM_ENABLED", "false")
    return raw.strip().lower() in ("true", "1", "yes", "on")


# ---------------------------------------------------------------------------
# Heuristic classification
# ---------------------------------------------------------------------------


def classify_encounter(encounter: Encounter) -> RouterResult:
    """
    Classify encounter into RcmStage using deterministic heuristics.
    Order of checks: denial/appeal -> eligibility -> prior auth -> coding (default).
    Keywords are loaded from routing_rules.yaml via get_heuristic_keywords().
    """
    notes_lower = (encounter.clinical_notes or "").lower()
    procedure_codes = {p.code for p in encounter.procedures}
    auth_cpt = get_auth_required_procedures()
    keywords = get_heuristic_keywords()
    denial_kw = keywords.get("denial_appeal", [])
    eligibility_kw = keywords.get("eligibility", [])

    def _result(stage: RcmStage, confidence: float, reasoning: str) -> RouterResult:
        logger.info(
            "Router classification",
            encounter_id=encounter.encounter_id,
            stage=stage.value,
            action="heuristic_classify",
            confidence=confidence,
            reasoning=reasoning,
        )
        return RouterResult(stage=stage, confidence=confidence, reasoning=reasoning)

    if encounter.denial_info is not None:
        return _result(RcmStage.DENIAL_APPEAL, 1.0, "Structured denial_info present; route to denial/appeal.")
    if any(kw in notes_lower for kw in denial_kw):
        return _result(RcmStage.DENIAL_APPEAL, 1.0, "Clinical notes mention denial or appeal; route to denial/appeal.")

    if any(kw in notes_lower for kw in eligibility_kw):
        return _result(
            RcmStage.ELIGIBILITY_VERIFICATION,
            1.0,
            "Notes indicate eligibility or coverage issues; route to eligibility verification.",
        )

    if procedure_codes & auth_cpt:
        return _result(
            RcmStage.PRIOR_AUTHORIZATION,
            1.0,
            f"Procedure code(s) {sorted(procedure_codes & auth_cpt)} require prior auth; route to prior authorization.",
        )

    if encounter.procedures and encounter.diagnoses:
        return _result(
            RcmStage.CODING_CHARGE_CAPTURE,
            0.95,
            "Procedures and diagnoses present; route to coding/charge capture.",
        )

    return _result(
        RcmStage.CODING_CHARGE_CAPTURE,
        0.7,
        "Default to coding/charge capture; incomplete or ambiguous encounter data.",
    )


# ---------------------------------------------------------------------------
# LLM-based classification
# ---------------------------------------------------------------------------

_LLM_ROUTER_SYSTEM_PROMPT = """\
You are an expert hospital Revenue Cycle Management (RCM) classifier.

Given a hospital encounter with patient demographics, insurance, procedures, diagnoses, \
and clinical notes, classify it into one or more RCM workflow stages.

Available stages:
- ELIGIBILITY_VERIFICATION: Insurance eligibility or coverage issues need checking
- PRIOR_AUTHORIZATION: Procedure requires prior auth from payer
- CODING_CHARGE_CAPTURE: Encounter needs coding and charge capture
- CLAIMS_SUBMISSION: Encounter is coded and ready for claim submission
- DENIAL_APPEAL: A prior claim was denied and needs appeal

Important rules:
1. An encounter may need MULTIPLE stages in sequence (e.g., eligibility check, then prior auth, then coding).
2. Return stages in execution order.
3. For each stage, provide confidence (0.0-1.0) and brief reasoning.

Respond ONLY with valid JSON in this exact format:
{
  "stages": [
    {"stage": "STAGE_NAME", "confidence": 0.95, "reasoning": "brief explanation"}
  ]
}
"""


def _build_encounter_prompt(encounter: Encounter) -> str:
    """Build a user prompt describing the encounter for LLM classification."""
    proc_str = ", ".join(f"{p.code} ({p.description})" for p in encounter.procedures) or "none"
    diag_str = ", ".join(f"{d.code} ({d.description})" for d in encounter.diagnoses) or "none"
    denial_str = "none"
    if encounter.denial_info:
        denial_str = (
            f"claim_id={encounter.denial_info.claim_id}, "
            f"reason_codes={encounter.denial_info.reason_codes}, "
            f"denial_date={encounter.denial_info.denial_date}"
        )

    return f"""\
Encounter ID: {encounter.encounter_id}
Date: {encounter.date}
Type: {encounter.type.value}
Patient: age={encounter.patient.age}, gender={encounter.patient.gender}
Insurance: payer={encounter.insurance.payer}, plan={encounter.insurance.plan_type}
Procedures: {proc_str}
Diagnoses: {diag_str}
Clinical Notes: {encounter.clinical_notes}
Denial Info: {denial_str}
Documents: {", ".join(encounter.documents) if encounter.documents else "none"}
"""


def _parse_llm_response(raw_text: str) -> list[dict[str, Any]]:
    """Parse LLM JSON response into list of stage dicts."""
    text = raw_text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [ln for ln in lines if not ln.strip().startswith("```")]
        text = "\n".join(lines)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("LLM router returned invalid JSON: %s", text[:200])
        return []
    stages = parsed.get("stages", [])
    if not isinstance(stages, list):
        return []
    return stages


def llm_classify_encounter(encounter: Encounter) -> MultiStageRouterResult | None:
    """
    Classify encounter using an LLM via litellm.completion.
    Returns None if LLM is unavailable or returns an unparsable response.
    """
    try:
        from litellm import completion
    except ImportError:
        logger.warning("litellm not installed; LLM router unavailable")
        return None

    llm_config = get_router_llm_config()
    model = llm_config.get("model", "gpt-4o-mini")
    user_prompt = _build_encounter_prompt(encounter)

    try:
        response = completion(
            model=model,
            messages=[
                {"role": "system", "content": _LLM_ROUTER_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
            max_tokens=500,
        )
        raw_text = response.choices[0].message.content or ""
    except Exception:
        logger.exception("LLM router call failed")
        return None

    stage_dicts = _parse_llm_response(raw_text)
    if not stage_dicts:
        return None

    stages: list[RcmStage] = []
    results: list[RouterResult] = []
    reasoning_parts: list[str] = []

    for sd in stage_dicts:
        if not isinstance(sd, dict):
            logger.warning("LLM returned non-dict stage entry: %s", sd)
            continue
        stage_name = sd.get("stage", "")
        try:
            stage = RcmStage(stage_name)
        except ValueError:
            logger.warning("LLM returned unknown stage: %s", stage_name)
            continue
        if stage in (RcmStage.INTAKE, RcmStage.HUMAN_ESCALATION):
            continue
        try:
            confidence = float(sd.get("confidence") or 0.5)
        except (TypeError, ValueError):
            confidence = 0.5
        reasoning = sd.get("reasoning", "")
        stages.append(stage)
        results.append(RouterResult(stage=stage, confidence=confidence, reasoning=reasoning))
        reasoning_parts.append(f"{stage.value}: {reasoning}")

    if not stages:
        return None

    return MultiStageRouterResult(
        stages=stages,
        results=results,
        reasoning="; ".join(reasoning_parts),
    )


# ---------------------------------------------------------------------------
# Multi-stage routing
# ---------------------------------------------------------------------------


def _needs_stage(encounter: Encounter, stage: RcmStage) -> bool:
    """Check if encounter needs a given downstream stage based on encounter data."""
    auth_cpt = get_auth_required_procedures()
    procedure_codes = {p.code for p in encounter.procedures}

    if stage == RcmStage.ELIGIBILITY_VERIFICATION:
        notes_lower = (encounter.clinical_notes or "").lower()
        keywords = get_heuristic_keywords()
        eligibility_kw = keywords.get("eligibility", [])
        return any(kw in notes_lower for kw in eligibility_kw)

    if stage == RcmStage.PRIOR_AUTHORIZATION:
        return bool(procedure_codes & auth_cpt)

    if stage == RcmStage.CODING_CHARGE_CAPTURE:
        return bool(encounter.procedures and encounter.diagnoses)

    if stage == RcmStage.CLAIMS_SUBMISSION:
        return bool(encounter.procedures and encounter.diagnoses)

    if stage == RcmStage.DENIAL_APPEAL:
        return encounter.denial_info is not None

    return False


def classify_encounter_multi_stage(encounter: Encounter) -> MultiStageRouterResult:
    """
    Determine all stages an encounter needs, using the primary heuristic
    classification plus multi-stage sequence expansion.

    For example, an MRI encounter might need:
    ELIGIBILITY_VERIFICATION -> PRIOR_AUTHORIZATION -> CODING_CHARGE_CAPTURE
    """
    primary = classify_encounter(encounter)
    stages: list[RcmStage] = [primary.stage]
    results: list[RouterResult] = [primary]

    sequences = get_multi_stage_sequences()
    downstream_stages = sequences.get(primary.stage.value, [])

    for stage_name in downstream_stages:
        try:
            stage = RcmStage(stage_name)
        except ValueError:
            continue
        if stage in stages:
            continue
        if _needs_stage(encounter, stage):
            result = RouterResult(
                stage=stage,
                confidence=0.85,
                reasoning=f"Downstream stage triggered after {primary.stage.value}.",
            )
            stages.append(stage)
            results.append(result)

    reasoning_parts = [f"{r.stage.value}: {r.reasoning}" for r in results]
    return MultiStageRouterResult(
        stages=stages,
        results=results,
        reasoning="; ".join(reasoning_parts),
    )


# ---------------------------------------------------------------------------
# Hybrid routing entry point
# ---------------------------------------------------------------------------


def route_encounter(encounter: Encounter) -> RouterResult:
    """
    Route encounter: run heuristics first; call LLM router when
    heuristic confidence is below threshold and LLM routing is enabled.
    Returns the primary stage RouterResult (for backward compatibility).
    """
    result = classify_encounter(encounter)
    llm_config = get_router_llm_config()
    threshold = float(llm_config.get("confidence_threshold", 0.9))

    if result.confidence < threshold and _llm_router_enabled():
        llm_result = llm_classify_encounter(encounter)
        if llm_result is not None and llm_result.results:
            llm_primary = llm_result.results[0]
            logger.info(
                "LLM router override: heuristic=%s(%.2f) -> llm=%s(%.2f)",
                result.stage.value,
                result.confidence,
                llm_primary.stage.value,
                llm_primary.confidence,
            )
            return llm_primary
    return result


def route_encounter_multi_stage(encounter: Encounter) -> MultiStageRouterResult:
    """
    Full multi-stage routing: heuristic multi-stage first, LLM fallback for
    low-confidence primary classification.
    """
    multi = classify_encounter_multi_stage(encounter)

    llm_config = get_router_llm_config()
    threshold = float(llm_config.get("confidence_threshold", 0.9))

    if multi.primary_confidence < threshold and _llm_router_enabled():
        llm_result = llm_classify_encounter(encounter)
        if llm_result is not None and llm_result.results:
            logger.info(
                "LLM router override (multi-stage): heuristic=%s -> llm=%s",
                [s.value for s in multi.stages],
                [s.value for s in llm_result.stages],
            )
            return llm_result

    return multi
