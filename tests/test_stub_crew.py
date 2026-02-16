"""Tests for stub crew (CLAIMS_SUBMISSION, DENIAL_APPEAL fallback)."""

import pytest

from rcm_agent.crews.stub import run_stub_crew
from rcm_agent.models import EncounterStatus, RcmStage


def test_stub_crew_claims_submission(encounter_001):
    """Stub with override_stage=CLAIMS_SUBMISSION returns CLAIM_SUBMITTED."""
    output = run_stub_crew(encounter_001, override_stage=RcmStage.CLAIMS_SUBMISSION)
    assert output.encounter_id == encounter_001.encounter_id
    assert output.stage == RcmStage.CLAIMS_SUBMISSION
    assert output.status == EncounterStatus.CLAIM_SUBMITTED
    assert output.raw_result.get("stub") is True


def test_stub_crew_denial_appeal(encounter_004):
    """Stub with override_stage=DENIAL_APPEAL returns NEEDS_REVIEW."""
    output = run_stub_crew(encounter_004, override_stage=RcmStage.DENIAL_APPEAL)
    assert output.stage == RcmStage.DENIAL_APPEAL
    assert output.status == EncounterStatus.NEEDS_REVIEW
    assert "denial" in output.message.lower() or "review" in output.message.lower()


def test_stub_crew_no_override_fallback_coded(encounter_001):
    """Stub with no override_stage falls back to CODING_CHARGE_CAPTURE / CODED."""
    output = run_stub_crew(encounter_001, override_stage=None)
    assert output.stage == RcmStage.CODING_CHARGE_CAPTURE
    assert output.status == EncounterStatus.CODED
