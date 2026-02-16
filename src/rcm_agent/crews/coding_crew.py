"""Coding and charge capture crew: suggest codes, validate, missing charges, reimbursement."""

from rcm_agent.models import Encounter, EncounterOutput, EncounterStatus, RcmStage
from rcm_agent.tools.coding import (
    calculate_expected_reimbursement,
    identify_missing_charges,
    suggest_codes,
    validate_code_combinations,
)


def run_coding_crew(encounter: Encounter) -> EncounterOutput:
    """
    Run coding workflow: suggest_codes -> validate_code_combinations -> identify_missing_charges -> calculate_expected_reimbursement.
    Returns EncounterOutput with status CODED and suggested codes, validation, reimbursement in raw_result.
    """
    actions: list[str] = ["suggest_codes"]
    existing_icd = [d.code for d in encounter.diagnoses]
    existing_cpt = [p.code for p in encounter.procedures]
    existing_codes = {"icd": existing_icd, "cpt": existing_cpt}

    suggestion = suggest_codes(
        encounter.clinical_notes or "",
        encounter.type,
        existing_codes=existing_codes,
    )
    icd_codes = [c["code"] for c in suggestion.get("icd_codes", [])] or existing_icd
    cpt_codes = suggestion.get("cpt_codes") or existing_cpt
    if not cpt_codes and existing_cpt:
        cpt_codes = existing_cpt

    actions.append("validate_code_combinations")
    validation = validate_code_combinations(icd_codes, cpt_codes)

    actions.append("identify_missing_charges")
    missing = identify_missing_charges(encounter, suggestion)

    actions.append("calculate_expected_reimbursement")
    reimbursement = calculate_expected_reimbursement(cpt_codes, encounter.insurance.payer)

    confidence = suggestion.get("confidence", 0.5)
    raw_result = {
        "suggested_codes": suggestion,
        "validation": validation,
        "missing_charges": missing,
        "reimbursement": reimbursement,
        "confidence": confidence,
    }

    return EncounterOutput(
        encounter_id=encounter.encounter_id,
        stage=RcmStage.CODING_CHARGE_CAPTURE,
        status=EncounterStatus.CODED,
        actions_taken=actions,
        artifacts=[],
        message=f"Coding complete; confidence={confidence:.2f}, expected reimbursement=${reimbursement['total_expected']:,.2f}.",
        raw_result=raw_result,
    )
