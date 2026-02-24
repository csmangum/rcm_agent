"""Denial and appeal crew: analyze denial codes, classify type, assess viability, generate appeal letter and packet."""

import json

from rcm_agent.models import Encounter, EncounterOutput, EncounterStatus, RcmStage
from rcm_agent.tools._types import DenialAnalysis
from rcm_agent.tools.appeal import (
    assemble_appeal_packet,
    generate_appeal_letter,
    search_payer_policies_for_appeal,
)
from rcm_agent.tools.denial import (
    assess_appeal_viability,
    classify_denial_type,
    parse_denial_reason_codes,
)
from rcm_agent.utils import save_artifact


def run_denial_appeal_crew(encounter: Encounter) -> EncounterOutput:
    """
    Run denial/appeal workflow: parse reason codes -> classify type -> assess viability ->
    (if viable) search policies -> generate letter -> assemble packet.
    Returns EncounterOutput with denial analysis and optional appeal artifacts.
    """
    actions: list[str] = ["parse_denial_reason_codes"]
    reason_codes = parse_denial_reason_codes(encounter)

    actions.append("classify_denial_type")
    denial_type = classify_denial_type(reason_codes)

    actions.append("assess_appeal_viability")
    appeal_viable, viability_summary = assess_appeal_viability(
        reason_codes, encounter
    )

    denial_analysis = DenialAnalysis(
        reason_codes=reason_codes,
        denial_type=denial_type,
        appeal_viable=appeal_viable,
        viability_summary=viability_summary,
    )

    claim_id = encounter.denial_info.claim_id if encounter.denial_info else None
    raw_result = {
        "reason_codes": reason_codes,
        "denial_type": denial_type,
        "appeal_viable": appeal_viable,
        "viability_summary": viability_summary,
        "claim_id": claim_id,
    }

    artifacts: list[str] = []
    status = EncounterStatus.CLAIM_DENIED
    message = viability_summary

    if appeal_viable:
        actions.append("search_payer_policies_for_appeal")
        policy_snippets: list[str] = []
        for p in encounter.procedures:
            policy_snippets.extend(
                search_payer_policies_for_appeal(
                    encounter.insurance.payer, p.code
                )
            )

        actions.append("generate_appeal_letter")
        letter_text = generate_appeal_letter(encounter, denial_analysis, policy_snippets)

        actions.append("assemble_appeal_packet")
        appeal_packet = assemble_appeal_packet(
            encounter, denial_analysis, letter_text
        )

        raw_result["appeal_packet"] = appeal_packet
        raw_result["letter_text"] = letter_text

        packet_filename = f"appeal_packet_{encounter.encounter_id}.json"
        letter_filename = f"appeal_letter_{encounter.encounter_id}.txt"
        save_artifact(
            encounter.encounter_id,
            packet_filename,
            json.dumps(appeal_packet, indent=2),
        )
        save_artifact(encounter.encounter_id, letter_filename, letter_text)
        artifacts = [packet_filename, letter_filename]
        status = EncounterStatus.NEEDS_REVIEW
        message = f"Appeal packet and letter prepared; {viability_summary}"
    else:
        message = f"Appeal not recommended. {viability_summary}"

    return EncounterOutput(
        encounter_id=encounter.encounter_id,
        stage=RcmStage.DENIAL_APPEAL,
        status=status,
        actions_taken=actions,
        artifacts=artifacts,
        message=message,
        raw_result=raw_result,
    )
