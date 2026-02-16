"""Coding and charge capture crew: suggest codes, validate, missing charges, reimbursement."""

import json

from rcm_agent.models import Encounter, EncounterOutput, EncounterStatus, RcmStage
from rcm_agent.tools.coding import (
    calculate_expected_reimbursement,
    identify_missing_charges,
    suggest_codes,
    validate_code_combinations,
)
from rcm_agent.utils import save_artifact


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
    raw_icd = suggestion.get("icd_codes") or []
    raw_cpt = suggestion.get("cpt_codes") or []
    icd_codes = [c["code"] for c in raw_icd if isinstance(c, dict) and "code" in c] or existing_icd
    cpt_codes = [c["code"] for c in raw_cpt if isinstance(c, dict) and "code" in c] if raw_cpt else existing_cpt

    actions.append("validate_code_combinations")
    validation = validate_code_combinations(icd_codes, cpt_codes)

    actions.append("identify_missing_charges")
    missing = identify_missing_charges(encounter, suggestion, effective_cpt_codes=cpt_codes)

    actions.append("calculate_expected_reimbursement")
    reimbursement = calculate_expected_reimbursement(cpt_codes, encounter.insurance.payer)

    confidence = suggestion.get("confidence", 0.5)
    has_validation_issues = not validation.get("valid", True)
    has_missing_charge_flags = bool(missing.get("missing_charge_flags"))
    status = (
        EncounterStatus.NEEDS_REVIEW
        if has_validation_issues or has_missing_charge_flags
        else EncounterStatus.CODED
    )
    raw_result = {
        "suggested_codes": suggestion,
        "validation": validation,
        "missing_charges": missing,
        "reimbursement": reimbursement,
        "confidence": confidence,
    }

    if status == EncounterStatus.NEEDS_REVIEW:
        message = (
            f"Coding complete with issues; confidence={confidence:.2f}. "
            "Validation or missing charge flags require human review."
        )
    else:
        message = (
            f"Coding complete; confidence={confidence:.2f}, "
            f"expected reimbursement=${reimbursement['total_expected']:,.2f}."
        )
    artifact_filename = f"coding_summary_{encounter.encounter_id}.json"
    save_artifact(encounter.encounter_id, artifact_filename, json.dumps(raw_result, indent=2))
    return EncounterOutput(
        encounter_id=encounter.encounter_id,
        stage=RcmStage.CODING_CHARGE_CAPTURE,
        status=status,
        actions_taken=actions,
        artifacts=[artifact_filename],
        message=message,
        raw_result=raw_result,
    )
