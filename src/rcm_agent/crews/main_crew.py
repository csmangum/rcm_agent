"""Main crew orchestration: route -> escalation gate -> crew dispatch."""

from rcm_agent.config import get_auth_required_procedures
from rcm_agent.crews.coding_crew import run_coding_crew
from rcm_agent.crews.denial_appeal_crew import run_denial_appeal_crew
from rcm_agent.crews.eligibility_crew import run_eligibility_crew
from rcm_agent.crews.prior_auth_crew import run_prior_auth_crew
from rcm_agent.crews.router import route_encounter
from rcm_agent.crews.stub import run_stub_crew
from rcm_agent.models import (
    Encounter,
    EncounterOutput,
    EncounterStatus,
    RcmStage,
)
from rcm_agent.tools.logic import check_escalation

# Rough estimated charges for common CPT codes (for high-value escalation check)
_CPT_ESTIMATE: dict[str, float] = {
    "99213": 150.0,
    "99223": 450.0,
    "73721": 800.0,
    "70450": 400.0,
    "72148": 600.0,
    "29881": 3500.0,
    "27130": 25000.0,  # total hip arthroplasty
    "99285": 650.0,
}
_DEFAULT_ESTIMATE = 500.0


def estimate_charges(encounter: Encounter) -> float:
    """Simple charge estimate from procedure codes (for escalation threshold check)."""
    total = 0.0
    for p in encounter.procedures:
        total += _CPT_ESTIMATE.get(p.code, _DEFAULT_ESTIMATE)
    return total if total > 0 else _DEFAULT_ESTIMATE


def dispatch_to_crew(encounter: Encounter, stage: RcmStage) -> EncounterOutput:
    """Dispatch to specialized crew by stage; stub for CLAIMS_SUBMISSION and INTAKE only."""
    if stage == RcmStage.ELIGIBILITY_VERIFICATION:
        return run_eligibility_crew(encounter)
    if stage == RcmStage.PRIOR_AUTHORIZATION:
        return run_prior_auth_crew(encounter)
    if stage == RcmStage.CODING_CHARGE_CAPTURE:
        return run_coding_crew(encounter)
    if stage == RcmStage.DENIAL_APPEAL:
        return run_denial_appeal_crew(encounter)
    return run_stub_crew(
        encounter,
        auth_required_cpt=get_auth_required_procedures(),
        override_stage=stage,
    )


def process_encounter(encounter: Encounter) -> EncounterOutput:
    """
    Full pipeline: route -> escalation check -> crew dispatch (stubbed in Phase 2).
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

    output = dispatch_to_crew(encounter, router_result.stage)
    # Attach router metadata to raw_result for audit
    output.raw_result["router_stage"] = router_result.stage.value
    output.raw_result["router_confidence"] = router_result.confidence
    output.raw_result["router_reasoning"] = router_result.reasoning
    return output
