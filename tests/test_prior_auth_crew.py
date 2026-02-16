"""Integration tests for prior authorization crew."""

import pytest

from rcm_agent.models import EncounterStatus, RcmStage
from rcm_agent.crews.prior_auth_crew import run_prior_auth_crew


def test_prior_auth_crew_enc_002_approved(encounter_002):
    output = run_prior_auth_crew(encounter_002)
    assert output.encounter_id == "ENC-002"
    assert output.stage == RcmStage.PRIOR_AUTHORIZATION
    assert output.status == EncounterStatus.AUTH_APPROVED
    assert "extract_clinical_indicators" in output.actions_taken
    assert "submit_auth_request" in output.actions_taken
    assert "poll_auth_status" in output.actions_taken
    assert output.raw_result.get("status_result", {}).get("decision") == "approved"
    assert len(output.artifacts) >= 1

