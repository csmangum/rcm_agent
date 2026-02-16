"""Stub crew dispatcher: returns mock EncounterOutput for unimplemented stages (CLAIMS_SUBMISSION, DENIAL_APPEAL)."""

from rcm_agent.models import (
    Encounter,
    EncounterOutput,
    EncounterStatus,
    RcmStage,
)


def run_stub_crew(
    encounter: Encounter,
    auth_required_cpt: set[str] | None = None,
    override_stage: RcmStage | None = None,
) -> EncounterOutput:
    """
    Return a mock output for the given stage. Used when router returns CLAIMS_SUBMISSION or DENIAL_APPEAL.
    When override_stage is set, use that stage and a default status; otherwise fallback to CODED.
    """
    if override_stage is not None:
        stage = override_stage
        status, message = _default_status_for_stage(stage)
    else:
        stage = RcmStage.CODING_CHARGE_CAPTURE
        status = EncounterStatus.CODED
        message = "Stub: mock result: coded."

    return EncounterOutput(
        encounter_id=encounter.encounter_id,
        stage=stage,
        status=status,
        actions_taken=["stub_router", "stub_workflow"],
        artifacts=[],
        message=message,
        raw_result={"stub": True, "stage": stage.value, "status": status.value},
    )


def _default_status_for_stage(stage: RcmStage) -> tuple[EncounterStatus, str]:
    """Default status and message when router provides stage (stub workflow)."""
    if stage == RcmStage.ELIGIBILITY_VERIFICATION:
        return EncounterStatus.ELIGIBLE, "Stub: eligibility verification; mock result: eligible."
    if stage == RcmStage.PRIOR_AUTHORIZATION:
        return EncounterStatus.AUTH_APPROVED, "Stub: prior auth; mock result: approved."
    if stage == RcmStage.CODING_CHARGE_CAPTURE:
        return EncounterStatus.CODED, "Stub: coding; mock result: coded."
    if stage == RcmStage.DENIAL_APPEAL:
        return EncounterStatus.NEEDS_REVIEW, "Stub: denial/appeal; mock result: needs review."
    if stage == RcmStage.CLAIMS_SUBMISSION:
        return EncounterStatus.CLAIM_SUBMITTED, "Stub: claims submission; mock result: submitted."
    if stage == RcmStage.INTAKE:
        return EncounterStatus.NEEDS_REVIEW, "Stub: intake; mock result: needs review."
    return EncounterStatus.NEEDS_REVIEW, f"Stub: stage {stage.value}; mock result: needs review."
