"""Prior authorization crew: orchestrate clinical extraction, policy search, auth packet, submit, poll."""

import json

from rcm_agent.models import Encounter, EncounterOutput, EncounterStatus, RcmStage
from rcm_agent.observability import get_logger
from rcm_agent.rag import get_payer_policy_backend
from rcm_agent.tools.prior_auth import (
    assemble_auth_packet,
    extract_clinical_indicators,
    poll_auth_status,
    search_payer_policies,
    submit_auth_request,
)
from rcm_agent.utils import save_artifact

logger = get_logger(__name__)


def run_prior_auth_crew(encounter: Encounter) -> EncounterOutput:
    """
    Run prior auth workflow: extract indicators -> search policies -> assemble -> submit -> poll.
    Returns EncounterOutput with AUTH_APPROVED/AUTH_DENIED and auth packet artifact.
    """
    logger.info(
        "Prior auth crew started",
        encounter_id=encounter.encounter_id,
        stage="PRIOR_AUTHORIZATION",
        action="crew_started",
    )
    actions: list[str] = ["extract_clinical_indicators"]
    clinical_indicators = extract_clinical_indicators(encounter.clinical_notes or "")

    policy_matches: dict[str, list[str]] = {}
    policy_backend = get_payer_policy_backend()
    for p in encounter.procedures:
        actions.append("search_payer_policies")
        policy_matches[p.code] = search_payer_policies(
            encounter.insurance.payer, p.code, backend=policy_backend or "mock"
        )

    actions.append("assemble_auth_packet")
    auth_packet = assemble_auth_packet(encounter, clinical_indicators, policy_matches)

    actions.append("submit_auth_request")
    submit_result = submit_auth_request(auth_packet)
    auth_id = submit_result["auth_id"]

    actions.append("poll_auth_status")
    status_result = poll_auth_status(auth_id)

    decision = status_result.get("decision") or "pending"
    encounter_status = EncounterStatus.AUTH_APPROVED if decision == "approved" else EncounterStatus.AUTH_DENIED
    if decision == "pending":
        encounter_status = EncounterStatus.AUTH_REQUIRED

    logger.info(
        "Prior auth complete",
        encounter_id=encounter.encounter_id,
        stage="PRIOR_AUTHORIZATION",
        action="auth_complete",
        result=decision,
        auth_id=auth_id,
    )

    artifact_json = json.dumps(auth_packet, indent=2)
    artifact_filename = f"prior_auth_request_{encounter.encounter_id}.json"
    save_artifact(encounter.encounter_id, artifact_filename, artifact_json)
    artifacts = [artifact_filename]

    return EncounterOutput(
        encounter_id=encounter.encounter_id,
        stage=RcmStage.PRIOR_AUTHORIZATION,
        status=encounter_status,
        actions_taken=actions,
        artifacts=artifacts,
        message=f"Prior auth {decision}; auth_id={auth_id}.",
        raw_result={
            "clinical_indicators": clinical_indicators,
            "auth_packet": auth_packet,
            "auth_packet_json": artifact_json,
            "submit_result": submit_result,
            "status_result": status_result,
            "auth_id": auth_id,
        },
    )
