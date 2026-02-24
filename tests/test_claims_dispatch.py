"""Test that claims submission is properly wired into the main crew dispatch."""

from rcm_agent.crews.main_crew import dispatch_to_crew
from rcm_agent.models import EncounterStatus, RcmStage


def test_dispatch_claims_submission_with_pipeline_context(encounter_001):
    """dispatch_to_crew with pipeline_context passes authorization_number to claims crew."""
    output = dispatch_to_crew(
        encounter_001,
        RcmStage.CLAIMS_SUBMISSION,
        pipeline_context={"authorization_number": "AUTH-XYZ"},
    )
    assert output.stage == RcmStage.CLAIMS_SUBMISSION
    claim_data = output.raw_result.get("claim_data", {})
    assert claim_data.get("authorization_number") == "AUTH-XYZ"


def test_dispatch_claims_submission(encounter_001):
    """dispatch_to_crew routes CLAIMS_SUBMISSION to the real crew, not stub."""
    output = dispatch_to_crew(encounter_001, RcmStage.CLAIMS_SUBMISSION)
    assert output.stage == RcmStage.CLAIMS_SUBMISSION
    assert output.status != EncounterStatus.NEEDS_REVIEW or "scrubbing" in output.message.lower()
    assert "stub" not in (output.raw_result.get("stage", "") or "")
    assert output.raw_result.get("stub") is not True
    assert "assemble_clean_claim" in output.actions_taken


def test_dispatch_claims_produces_artifacts(encounter_003):
    output = dispatch_to_crew(encounter_003, RcmStage.CLAIMS_SUBMISSION)
    assert len(output.artifacts) >= 1
    assert any("claim_837" in a for a in output.artifacts)
