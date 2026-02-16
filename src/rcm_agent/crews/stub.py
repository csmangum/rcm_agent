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
) -> EncounterOutput:
    """
    Determine a plausible RcmStage from encounter data and return a mock output.
    Replaced by real CrewAI orchestration in Phase 2.
    """
    auth_cpt = auth_required_cpt or DEFAULT_AUTH_REQUIRED_CPT
    notes_lower = (encounter.clinical_notes or "").lower()
    procedure_codes = {p.code for p in encounter.procedures}

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
