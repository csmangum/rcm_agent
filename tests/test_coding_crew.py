"""Integration tests for coding and charge capture crew."""

import pytest

from rcm_agent.models import EncounterStatus, RcmStage
from rcm_agent.crews.coding_crew import run_coding_crew


def test_coding_crew_enc_001_coded(encounter_001):
    output = run_coding_crew(encounter_001)
    assert output.encounter_id == "ENC-001"
    assert output.stage == RcmStage.CODING_CHARGE_CAPTURE
    assert output.status == EncounterStatus.CODED
    assert "suggest_codes" in output.actions_taken
    assert "validate_code_combinations" in output.actions_taken
    assert "calculate_expected_reimbursement" in output.actions_taken
    assert "suggested_codes" in output.raw_result
    assert "reimbursement" in output.raw_result
    assert "confidence" in output.raw_result
