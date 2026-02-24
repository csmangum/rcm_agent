"""Main crew orchestration: route -> escalation gate -> crew dispatch.

Supports both single-stage (process_encounter) and multi-stage
(process_encounter_multi_stage) pipelines.
"""

from __future__ import annotations

import logging
from typing import Any

from rcm_agent.config import CPT_CHARGE_AMOUNTS, get_auth_required_procedures
from rcm_agent.crews.claims_submission_crew import run_claims_submission_crew
from rcm_agent.crews.coding_crew import run_coding_crew
from rcm_agent.crews.denial_appeal_crew import run_denial_appeal_crew
from rcm_agent.crews.eligibility_crew import run_eligibility_crew
from rcm_agent.crews.prior_auth_crew import run_prior_auth_crew
from rcm_agent.crews.router import (
    MultiStageRouterResult,
    route_encounter,
    route_encounter_multi_stage,
)
from rcm_agent.crews.stub import run_stub_crew
from rcm_agent.models import (
    Encounter,
    EncounterOutput,
    EncounterStatus,
    PipelineContext,
    RcmStage,
)
from rcm_agent.tools.logic import check_escalation

logger = logging.getLogger(__name__)

_DEFAULT_ESTIMATE = 500.0


def estimate_charges(encounter: Encounter) -> float:
    """Simple charge estimate from procedure codes (for escalation threshold check)."""
    total = 0.0
    for p in encounter.procedures:
        total += CPT_CHARGE_AMOUNTS.get(p.code, _DEFAULT_ESTIMATE)
    return total if total > 0 else _DEFAULT_ESTIMATE


def dispatch_to_crew(
    encounter: Encounter,
    stage: RcmStage,
    pipeline_context: PipelineContext | None = None,
) -> EncounterOutput:
    """Dispatch to specialized crew by stage; stub for INTAKE only."""
    if stage == RcmStage.ELIGIBILITY_VERIFICATION:
        return run_eligibility_crew(encounter)
    if stage == RcmStage.PRIOR_AUTHORIZATION:
        return run_prior_auth_crew(encounter)
    if stage == RcmStage.CODING_CHARGE_CAPTURE:
        return run_coding_crew(encounter)
    if stage == RcmStage.CLAIMS_SUBMISSION:
        pc = pipeline_context or {}
        return run_claims_submission_crew(
            encounter,
            coding_result=pc.get("coding_result"),
            authorization_number=pc.get("authorization_number"),
        )
    if stage == RcmStage.DENIAL_APPEAL:
        return run_denial_appeal_crew(encounter)
    return run_stub_crew(
        encounter,
        auth_required_cpt=get_auth_required_procedures(),
        override_stage=stage,
    )


def _build_pipeline_context_from_output(output: EncounterOutput) -> dict[str, Any]:
    """Extract pipeline context from a crew output to pass to downstream stages."""
    ctx: dict[str, Any] = {}
    if output.stage == RcmStage.CODING_CHARGE_CAPTURE:
        ctx["coding_result"] = output.raw_result
    if output.stage == RcmStage.PRIOR_AUTHORIZATION:
        auth_num = output.raw_result.get("authorization_number") or output.raw_result.get("auth_id")
        if auth_num:
            ctx["authorization_number"] = auth_num
    return ctx


def process_encounter(
    encounter: Encounter,
    pipeline_context: PipelineContext | None = None,
) -> EncounterOutput:
    """
    Single-stage pipeline: route -> escalation check -> crew dispatch.
    Backward-compatible entry point.
    """
    router_result = route_encounter(encounter)
    estimated_charges = estimate_charges(encounter)

    escalation = check_escalation(
        encounter,
        confidence=router_result.confidence,
        estimated_charges=estimated_charges,
    )
    if escalation is not None:
        return EncounterOutput(
            encounter_id=encounter.encounter_id,
            stage=RcmStage.HUMAN_ESCALATION,
            status=EncounterStatus.NEEDS_REVIEW,
            actions_taken=["router", "escalation_check"],
            artifacts=[],
            message=escalation.message,
            raw_result={
                "escalation_reasons": escalation.reasons,
                "router_stage": router_result.stage.value,
                "router_confidence": router_result.confidence,
                "router_reasoning": router_result.reasoning,
            },
        )

    output = dispatch_to_crew(encounter, router_result.stage, pipeline_context)
    output.raw_result["router_stage"] = router_result.stage.value
    output.raw_result["router_confidence"] = router_result.confidence
    output.raw_result["router_reasoning"] = router_result.reasoning
    return output


def process_encounter_multi_stage(
    encounter: Encounter,
    pipeline_context: PipelineContext | None = None,
) -> list[EncounterOutput]:
    """
    Multi-stage pipeline: route to multiple stages in sequence.

    Runs escalation check on the primary stage. If no escalation, executes
    each stage in order, passing context from prior stage outputs to downstream
    stages (e.g., coding_result, authorization_number).

    Returns a list of EncounterOutput, one per executed stage.
    """
    multi_result: MultiStageRouterResult = route_encounter_multi_stage(encounter)
    estimated_charges = estimate_charges(encounter)

    escalation = check_escalation(
        encounter,
        confidence=multi_result.primary_confidence,
        estimated_charges=estimated_charges,
    )
    if escalation is not None:
        return [
            EncounterOutput(
                encounter_id=encounter.encounter_id,
                stage=RcmStage.HUMAN_ESCALATION,
                status=EncounterStatus.NEEDS_REVIEW,
                actions_taken=["router", "escalation_check"],
                artifacts=[],
                message=escalation.message,
                raw_result={
                    "escalation_reasons": escalation.reasons,
                    "router_stages": [s.value for s in multi_result.stages],
                    "router_confidence": multi_result.primary_confidence,
                    "router_reasoning": multi_result.reasoning,
                },
            )
        ]

    outputs: list[EncounterOutput] = []
    accumulated_context: dict[str, Any] = dict(pipeline_context) if pipeline_context else {}

    for i, stage in enumerate(multi_result.stages):
        logger.info(
            "Multi-stage pipeline [%d/%d]: %s for %s",
            i + 1,
            len(multi_result.stages),
            stage.value,
            encounter.encounter_id,
        )
        pc: PipelineContext = {}
        if "coding_result" in accumulated_context:
            pc["coding_result"] = accumulated_context["coding_result"]
        if "authorization_number" in accumulated_context:
            pc["authorization_number"] = accumulated_context["authorization_number"]

        output = dispatch_to_crew(encounter, stage, pc or None)
        output.raw_result["router_stage"] = stage.value
        output.raw_result["router_confidence"] = multi_result.results[i].confidence
        output.raw_result["router_reasoning"] = multi_result.results[i].reasoning
        output.raw_result["pipeline_position"] = i + 1
        output.raw_result["pipeline_total_stages"] = len(multi_result.stages)
        outputs.append(output)

        accumulated_context.update(_build_pipeline_context_from_output(output))

        is_failure = output.status in (
            EncounterStatus.NOT_ELIGIBLE,
            EncounterStatus.AUTH_DENIED,
            EncounterStatus.CLAIM_DENIED,
        )
        if is_failure:
            logger.warning(
                "Multi-stage pipeline halted at stage %s (%s) for %s",
                stage.value,
                output.status.value,
                encounter.encounter_id,
            )
            break

    return outputs
