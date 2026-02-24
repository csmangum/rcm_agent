"""Eligibility verification crew: orchestrate eligibility tools and return EncounterOutput."""

from rcm_agent.models import Encounter, EncounterOutput, EncounterStatus, RcmStage
from rcm_agent.observability.logging import get_logger
from rcm_agent.tools.eligibility import (
    check_coordination_of_benefits,
    check_member_eligibility,
    flag_coverage_gaps,
    verify_benefits,
)

logger = get_logger(__name__)


def run_eligibility_crew(encounter: Encounter) -> EncounterOutput:
    """
    Run eligibility verification: check eligibility -> verify benefits -> COB -> flag gaps.
    Returns EncounterOutput with ELIGIBLE/NOT_ELIGIBLE and coverage details in raw_result.
    """
    logger.info(
        "Eligibility crew started",
        encounter_id=encounter.encounter_id,
        stage="ELIGIBILITY_VERIFICATION",
        action="crew_started",
    )
    actions: list[str] = ["check_member_eligibility"]
    payer = encounter.insurance.payer
    member_id = encounter.insurance.member_id
    procedure_codes = [p.code for p in encounter.procedures]

    eligibility_result = check_member_eligibility(payer, member_id, encounter.date)
    raw_result: dict = {"eligibility": eligibility_result}

    if not eligibility_result.get("eligible", True):
        logger.info(
            "Eligibility check complete - not eligible",
            encounter_id=encounter.encounter_id,
            stage="ELIGIBILITY_VERIFICATION",
            action="check_complete",
            result="not_eligible",
        )
        gaps = flag_coverage_gaps(eligibility_result)
        cob = check_coordination_of_benefits(encounter.patient, encounter.insurance)
        raw_result["coordination_of_benefits"] = cob
        raw_result["coverage_gaps"] = gaps
        return EncounterOutput(
            encounter_id=encounter.encounter_id,
            stage=RcmStage.ELIGIBILITY_VERIFICATION,
            status=EncounterStatus.NOT_ELIGIBLE,
            actions_taken=[*actions, "flag_coverage_gaps", "check_coordination_of_benefits"],
            artifacts=[f"eligibility_gaps: {', '.join(gaps)}"] if gaps else [],
            message="Eligibility check: coverage lapsed or terminated.",
            raw_result=raw_result,
        )

    actions.append("verify_benefits")
    benefits_result = verify_benefits(payer, member_id, procedure_codes)
    raw_result["benefits"] = benefits_result

    actions.append("check_coordination_of_benefits")
    cob = check_coordination_of_benefits(encounter.patient, encounter.insurance)
    raw_result["coordination_of_benefits"] = cob

    actions.append("flag_coverage_gaps")
    gaps = flag_coverage_gaps(eligibility_result)
    raw_result["coverage_gaps"] = gaps

    status = EncounterStatus.ELIGIBLE if not gaps else EncounterStatus.NEEDS_REVIEW
    artifacts: list[str] = []
    if gaps:
        artifacts.append(f"coverage_gaps: {', '.join(gaps)}")
    if cob.get("has_secondary"):
        artifacts.append(cob.get("secondary_note") or "COB indicated")

    message = (
        "Eligibility verified; recommendation: proceed."
        if not gaps
        else "Eligibility verified with coverage gaps; recommendation: hold. Human review recommended."
    )
    logger.info(
        "Eligibility check complete",
        encounter_id=encounter.encounter_id,
        stage="ELIGIBILITY_VERIFICATION",
        action="check_complete",
        result="eligible" if not gaps else "needs_review",
        has_gaps=bool(gaps),
    )
    return EncounterOutput(
        encounter_id=encounter.encounter_id,
        stage=RcmStage.ELIGIBILITY_VERIFICATION,
        status=status,
        actions_taken=actions,
        artifacts=artifacts,
        message=message,
        raw_result=raw_result,
    )
