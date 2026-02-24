"""Unit tests for denial/appeal crew."""

import json
from pathlib import Path

from rcm_agent.crews.denial_appeal_crew import run_denial_appeal_crew
from rcm_agent.models import DenialInfo, Encounter, EncounterStatus, RcmStage


def _load_encounter(examples_dir: Path, filename: str) -> Encounter:
    with open(examples_dir / filename, encoding="utf-8") as f:
        return Encounter.model_validate(json.load(f))


def test_run_denial_appeal_crew_enc_004(examples_dir: Path) -> None:
    """run_denial_appeal_crew on ENC-004 produces denial analysis and appeal artifacts."""
    encounter = _load_encounter(examples_dir, "encounter_004_denial_scenario.json")
    output = run_denial_appeal_crew(encounter)
    assert output.encounter_id == "ENC-004"
    assert output.stage == RcmStage.DENIAL_APPEAL
    assert output.status in (EncounterStatus.NEEDS_REVIEW, EncounterStatus.CLAIM_DENIED)
    assert "parse_denial_reason_codes" in output.actions_taken
    assert "classify_denial_type" in output.actions_taken
    assert "assess_appeal_viability" in output.actions_taken
    assert output.raw_result.get("reason_codes") == ["CO-4", "PR-96"]
    assert output.raw_result.get("denial_type") in ("clinical", "administrative")
    assert "appeal_viable" in output.raw_result
    assert output.raw_result.get("claim_id") == "CLM-004"
    # Appeal viable with docs -> letter and packet
    assert "appeal_packet" in output.raw_result
    assert "letter_text" in output.raw_result
    assert len(output.artifacts) >= 1
    assert any("appeal_packet" in a for a in output.artifacts)
    assert any("appeal_letter" in a for a in output.artifacts)


def test_run_denial_appeal_crew_artifacts_list(examples_dir: Path) -> None:
    """Crew returns artifact filenames for appeal packet and letter."""
    encounter = _load_encounter(examples_dir, "encounter_004_denial_scenario.json")
    output = run_denial_appeal_crew(encounter)
    assert output.artifacts
    assert any("appeal_packet" in a for a in output.artifacts)
    assert any("appeal_letter" in a for a in output.artifacts)


def test_run_denial_appeal_crew_not_viable_no_letter() -> None:
    """When appeal not viable, no letter/packet artifact, message indicates not recommended."""
    encounter = Encounter(
        encounter_id="ENC-DUP",
        patient={"age": 30, "gender": "F", "zip": "10001"},
        insurance={"payer": "Aetna", "member_id": "M1", "plan_type": "PPO"},
        date="2026-01-01",
        type="office_visit",
        procedures=[],
        diagnoses=[],
        clinical_notes="Duplicate claim.",
        documents=[],
        denial_info=DenialInfo(claim_id="CLM-DUP", reason_codes=["CO-18"], denial_date=None),
    )
    output = run_denial_appeal_crew(encounter)
    assert output.stage == RcmStage.DENIAL_APPEAL
    assert output.raw_result.get("appeal_viable") is False
    assert "appeal_packet" not in output.raw_result
    assert len(output.artifacts) == 0
    assert "not recommended" in output.message.lower() or "duplicate" in output.message.lower()
