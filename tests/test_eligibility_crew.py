"""Integration tests for eligibility verification crew."""

import pytest

from rcm_agent.models import EncounterStatus, RcmStage
from rcm_agent.crews.eligibility_crew import run_eligibility_crew


def test_eligibility_crew_enc_001_eligible(encounter_001):
    output = run_eligibility_crew(encounter_001)
    assert output.encounter_id == "ENC-001"
    assert output.stage == RcmStage.ELIGIBILITY_VERIFICATION
    assert output.status == EncounterStatus.ELIGIBLE
    assert "check_member_eligibility" in output.actions_taken
    assert "verify_benefits" in output.actions_taken
    assert output.raw_result.get("eligibility", {}).get("eligible") is True


def test_eligibility_crew_enc_005_not_eligible(encounter_005):
    output = run_eligibility_crew(encounter_005)
    assert output.encounter_id == "ENC-005"
    assert output.stage == RcmStage.ELIGIBILITY_VERIFICATION
    assert output.status == EncounterStatus.NOT_ELIGIBLE
    assert output.raw_result.get("eligibility", {}).get("eligible") is False
    assert "coverage_gaps" in output.raw_result

