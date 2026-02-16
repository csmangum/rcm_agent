"""Stub crew dispatcher: returns mock EncounterOutput based on encounter data."""

from rcm_agent.models import (
    Encounter,
    EncounterOutput,
    EncounterStatus,
    RcmStage,
)

# CPT codes that typically require prior auth (subset; can be overridden by config later)
DEFAULT_AUTH_REQUIRED_CPT = {"73721", "70450", "72148", "29881"}


def run_stub_crew(
    encounter: Encounter,
    auth_required_cpt: set[str] | None = None,
    override_stage: RcmStage | None = None,
) -> EncounterOutput:
    """
    Determine a plausible RcmStage from encounter data and return a mock output.
    When override_stage is set (e.g. from router), use that stage and a default status.
    """
    auth_cpt = auth_required_cpt or DEFAULT_AUTH_REQUIRED_CPT
    notes_lower = (encounter.clinical_notes or "").lower()
    procedure_codes = {p.code for p in encounter.procedures}

    if override_stage is not None:
        stage = override_stage
        status, message = _default_status_for_stage(stage)
    else:
        # Heuristics (mirror Phase 2 router logic)
        if "denial" in notes_lower or "appeal" in notes_lower:
            stage = RcmStage.DENIAL_APPEAL
            status = EncounterStatus.NEEDS_REVIEW
            message = "Stub: routed to denial/appeal (mentioned in notes)."
        elif "lapsed" in notes_lower or "termination" in notes_lower:
            stage = RcmStage.ELIGIBILITY_VERIFICATION
            status = EncounterStatus.NOT_ELIGIBLE
            message = "Stub: routed to eligibility verification; mock result: not eligible (coverage lapsed/terminated)."
        elif "eligibility" in notes_lower:
            stage = RcmStage.ELIGIBILITY_VERIFICATION
            status = EncounterStatus.ELIGIBLE
            message = "Stub: routed to eligibility verification; mock result: eligible."
        elif procedure_codes & auth_cpt:
            stage = RcmStage.PRIOR_AUTHORIZATION
            status = EncounterStatus.AUTH_APPROVED
            message = "Stub: procedure requires prior auth; mock result: approved."
        elif encounter.type.value == "office_visit" and encounter.procedures and encounter.diagnoses:
            stage = RcmStage.CODING_CHARGE_CAPTURE
            status = EncounterStatus.CODED
            message = "Stub: coding complete; mock result: coded."
        else:
            stage = RcmStage.CODING_CHARGE_CAPTURE
            status = EncounterStatus.CODED
            message = "Stub: routed to coding; mock result: coded."

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
    return EncounterStatus.NEEDS_REVIEW, f"Stub: stage {stage.value}; mock result: needs review."
