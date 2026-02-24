"""Claims submission crew: assemble claim, scrub, submit, track remittance.

Agents: claim_assembler, scrubber, submission_tracker.
Closes the full RCM cycle: intake -> eligibility -> prior auth -> coding -> **claim submission** -> denial/appeal.
"""

import json
from typing import Any

from rcm_agent.models import Encounter, EncounterOutput, EncounterStatus, RcmStage
from rcm_agent.tools.claims import (
    assemble_clean_claim,
    check_remit_status,
    scrub_claim,
    submit_claim,
)
from rcm_agent.utils import save_artifact


def run_claims_submission_crew(
    encounter: Encounter,
    coding_result: dict[str, Any] | None = None,
    authorization_number: str | None = None,
) -> EncounterOutput:
    """Run claims submission workflow: assemble -> scrub -> submit -> track remittance.

    Args:
        encounter: The encounter to submit a claim for.
        coding_result: Optional output from the coding crew (suggested_codes, validation, etc.).
        authorization_number: Optional prior-auth number to attach to the claim.

    Returns:
        EncounterOutput with CLAIM_SUBMITTED / CLAIM_ACCEPTED / NEEDS_REVIEW status
        and 837-style claim + remittance summary artifacts.
    """
    actions: list[str] = []
    artifacts: list[str] = []

    # --- Agent 1: claim_assembler ---
    actions.append("assemble_clean_claim")
    claim_data = assemble_clean_claim(
        encounter,
        coding_result=coding_result,
        authorization_number=authorization_number,
    )

    claim_artifact = f"claim_837_{encounter.encounter_id}.json"
    save_artifact(encounter.encounter_id, claim_artifact, json.dumps(dict(claim_data), indent=2))
    artifacts.append(claim_artifact)

    # --- Agent 2: scrubber ---
    actions.append("scrub_claim")
    scrub_result = scrub_claim(claim_data)

    if scrub_result.get("edit_actions"):
        for edit in scrub_result["edit_actions"]:
            actions.append(f"auto_edit:{edit.split(':')[0]}")

    if not scrub_result["clean"]:
        error_summary = "; ".join(e["message"] for e in scrub_result["errors"])
        return EncounterOutput(
            encounter_id=encounter.encounter_id,
            stage=RcmStage.CLAIMS_SUBMISSION,
            status=EncounterStatus.NEEDS_REVIEW,
            actions_taken=actions,
            artifacts=artifacts,
            message=f"Claim failed scrubbing: {error_summary}",
            raw_result={
                "claim_data": dict(claim_data),
                "scrub_result": dict(scrub_result),
            },
        )

    # --- Agent 3: submission_tracker ---
    actions.append("submit_claim")
    submit_result = submit_claim(claim_data)
    claim_id = submit_result["claim_id"]

    actions.append("check_remit_status")
    remit_result = check_remit_status(claim_id)

    remit_artifact = f"remittance_835_{encounter.encounter_id}.json"
    remit_summary = _build_remittance_summary(encounter, claim_data, submit_result, remit_result)
    save_artifact(encounter.encounter_id, remit_artifact, json.dumps(remit_summary, indent=2))
    artifacts.append(remit_artifact)

    remit_status = remit_result.get("status", "pending")
    if remit_status == "paid":
        encounter_status = EncounterStatus.CLAIM_ACCEPTED
        paid = remit_result.get("paid_amount", 0.0)
        message = f"Claim {claim_id} accepted and paid ${paid:,.2f}; tracking={submit_result.get('tracking_number')}."
    elif remit_status == "denied":
        encounter_status = EncounterStatus.CLAIM_DENIED
        message = f"Claim {claim_id} denied by payer; see remittance for CARC/RARC details."
    else:
        encounter_status = EncounterStatus.CLAIM_SUBMITTED
        message = f"Claim {claim_id} submitted; remittance pending."

    return EncounterOutput(
        encounter_id=encounter.encounter_id,
        stage=RcmStage.CLAIMS_SUBMISSION,
        status=encounter_status,
        actions_taken=actions,
        artifacts=artifacts,
        message=message,
        raw_result={
            "claim_data": dict(claim_data),
            "scrub_result": dict(scrub_result),
            "submit_result": dict(submit_result),
            "remit_result": dict(remit_result),
            "claim_id": claim_id,
        },
    )


def _build_remittance_summary(
    encounter: Encounter,
    claim_data: dict[str, Any],
    submit_result: dict[str, Any],
    remit_result: dict[str, Any],
) -> dict[str, Any]:
    """Build a human-readable remittance summary combining claim and 835 data."""
    return {
        "encounter_id": encounter.encounter_id,
        "claim_id": submit_result.get("claim_id"),
        "tracking_number": submit_result.get("tracking_number"),
        "payer": encounter.insurance.payer,
        "member_id": encounter.insurance.member_id,
        "date_of_service": encounter.date,
        "total_charges": claim_data.get("total_charges"),
        "allowed_amount": remit_result.get("allowed_amount"),
        "paid_amount": remit_result.get("paid_amount"),
        "patient_responsibility": remit_result.get("patient_responsibility"),
        "adjustments": remit_result.get("adjustments", []),
        "check_number": remit_result.get("check_number"),
        "remit_date": remit_result.get("remit_date"),
        "status": remit_result.get("status"),
        "line_items": claim_data.get("line_items", []),
    }
