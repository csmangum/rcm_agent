"""Claims submission tools: claim assembly, scrubbing, submission, and remittance status."""

from typing import Any

from rcm_agent.config import CPT_CHARGE_AMOUNTS, DEFAULT_CHARGE
from rcm_agent.integrations.registry import get_claims_backend
from rcm_agent.models import Encounter, EncounterType
from rcm_agent.tools._types import (
    ClaimLineItem,
    CleanClaimData,
    RemitStatusResult,
    ScrubResult,
    SubmitClaimResult,
)

# Mock NPI keyed by provider/facility; real implementation would look up from config or encounter.
_MOCK_NPI = "1234567890"

# Place of service codes mapped from EncounterType.
_POS_MAP: dict[str, str] = {
    EncounterType.office_visit: "11",
    EncounterType.outpatient_procedure: "22",
    EncounterType.inpatient: "21",
    EncounterType.emergency: "23",
}


def assemble_clean_claim(
    encounter: Encounter,
    coding_result: dict[str, Any] | None = None,
    authorization_number: str | None = None,
) -> CleanClaimData:
    """Assemble an 837-style clean claim from encounter data and optional coding results.

    If coding_result is provided, its suggested codes are merged with the encounter's
    existing procedure/diagnosis codes.  Returns a CleanClaimData ready for scrubbing.
    """
    icd_codes = [d.code for d in encounter.diagnoses]
    cpt_codes = [p.code for p in encounter.procedures]
    modifiers: list[str] = []

    if coding_result:
        for c in coding_result.get("icd_codes") or []:
            code = c["code"] if isinstance(c, dict) else c
            if code not in icd_codes:
                icd_codes.append(code)
        for c in coding_result.get("cpt_codes") or []:
            code = c["code"] if isinstance(c, dict) else c
            if code not in cpt_codes:
                cpt_codes.append(code)
        for ms in (coding_result.get("validation") or {}).get("modifier_suggestions") or []:
            mod = ms.get("modifier") if isinstance(ms, dict) else ms
            if mod and mod not in modifiers:
                modifiers.append(mod)

    if "27130" in cpt_codes and "99223" in cpt_codes and "57" not in modifiers:
        modifiers.append("57")

    place_of_service = _POS_MAP.get(encounter.type, "11")

    line_items: list[ClaimLineItem] = []
    total_charges = 0.0
    for idx, cpt in enumerate(cpt_codes, start=1):
        charge = CPT_CHARGE_AMOUNTS.get(cpt, DEFAULT_CHARGE)
        total_charges += charge
        line_mods: list[str] = []
        if cpt == "99223" and "57" in modifiers:
            line_mods.append("57")
        line_items.append(
            ClaimLineItem(
                line_number=idx,
                cpt_code=cpt,
                description=_description_for_cpt(encounter, cpt),
                icd_pointers=icd_codes[:4],
                modifiers=line_mods,
                units=1,
                charge_amount=charge,
            )
        )

    return CleanClaimData(
        encounter_id=encounter.encounter_id,
        billing_provider_npi=_MOCK_NPI,
        payer=encounter.insurance.payer,
        member_id=encounter.insurance.member_id,
        patient=encounter.patient.model_dump(),
        date_of_service=encounter.date,
        place_of_service=place_of_service,
        icd_codes=icd_codes,
        cpt_codes=cpt_codes,
        modifiers=modifiers,
        line_items=line_items,
        total_charges=round(total_charges, 2),
        authorization_number=authorization_number,
    )


def _description_for_cpt(encounter: Encounter, cpt: str) -> str:
    for p in encounter.procedures:
        if p.code == cpt:
            return p.description
    return cpt


def scrub_claim(claim_data: CleanClaimData | dict[str, Any]) -> ScrubResult:
    """Run pre-submission edits/validation via the configured claims backend."""
    result = get_claims_backend().scrub_claim(dict(claim_data))
    return ScrubResult(
        clean=result["clean"],
        errors=result.get("errors", []),
        warnings=result.get("warnings", []),
        edit_actions=result.get("edit_actions", []),
    )


def submit_claim(claim_data: CleanClaimData | dict[str, Any]) -> SubmitClaimResult:
    """Submit a claim via the configured claims backend."""
    result = get_claims_backend().submit_claim(dict(claim_data))
    return SubmitClaimResult(
        claim_id=result["claim_id"],
        status=result["status"],
        submitted_at=result["submitted_at"],
        message=result.get("message", ""),
        tracking_number=result.get("tracking_number"),
    )


def check_remit_status(claim_id: str) -> RemitStatusResult:
    """Check remittance / payment status for a submitted claim."""
    result = get_claims_backend().get_remit(claim_id)
    return RemitStatusResult(
        claim_id=result["claim_id"],
        status=result["status"],
        paid_amount=result.get("paid_amount"),
        allowed_amount=result.get("allowed_amount"),
        patient_responsibility=result.get("patient_responsibility"),
        adjustments=result.get("adjustments", []),
        check_number=result.get("check_number"),
        remit_date=result.get("remit_date"),
    )
