"""Unit tests for escalation logic."""

import pytest

from rcm_agent.models import DiagnosisCode, Encounter, EncounterStatus, RcmStage
from rcm_agent.tools.logic import check_escalation


@pytest.fixture
def clean_encounter(sample_encounter_json: dict) -> Encounter:
    """Routine visit with notes and documents (no escalation)."""
    return Encounter.model_validate(sample_encounter_json)


def test_no_escalation_clean_encounter(clean_encounter: Encounter) -> None:
    """Clean encounter with notes and documents does not escalate."""
    result = check_escalation(
        clean_encounter,
        confidence=0.9,
        estimated_charges=200.0,
    )
    assert result is None


def test_escalation_low_confidence(clean_encounter: Encounter, monkeypatch: pytest.MonkeyPatch) -> None:
    """Low confidence triggers escalation."""
    monkeypatch.setenv("ESCALATION_CONFIDENCE_THRESHOLD", "0.85")
    result = check_escalation(
        clean_encounter,
        confidence=0.72,
        estimated_charges=200.0,
    )
    assert result is not None
    assert result.encounter_id == clean_encounter.encounter_id
    assert result.stage == RcmStage.HUMAN_ESCALATION
    assert result.status == EncounterStatus.NEEDS_REVIEW
    assert any("0.72" in r and "0.85" in r for r in result.reasons)


def test_escalation_high_value(clean_encounter: Encounter, monkeypatch: pytest.MonkeyPatch) -> None:
    """Estimated charges above threshold trigger escalation."""
    monkeypatch.setenv("ESCALATION_HIGH_VALUE_THRESHOLD", "5000")
    result = check_escalation(
        clean_encounter,
        confidence=0.95,
        estimated_charges=6000.0,
    )
    assert result is not None
    assert any("6000" in r.replace(",", "") and "5000" in r.replace(",", "") for r in result.reasons)


def test_escalation_oncology_icd(clean_encounter: Encounter, monkeypatch: pytest.MonkeyPatch) -> None:
    """Oncology ICD code triggers escalation when flag enabled."""
    monkeypatch.setenv("ESCALATION_ONCOLOGY_FLAG", "true")
    encounter = clean_encounter.model_copy(
        update={
            "diagnoses": [
                DiagnosisCode(code="C50.911", description="Malignant neoplasm of right breast"),
            ],
        },
    )
    result = check_escalation(encounter, confidence=0.95, estimated_charges=100.0)
    assert result is not None
    assert any("oncology" in r.lower() or "ICD" in r for r in result.reasons)


def test_escalation_oncology_notes(clean_encounter: Encounter, monkeypatch: pytest.MonkeyPatch) -> None:
    """Clinical notes mentioning cancer trigger escalation when flag enabled."""
    monkeypatch.setenv("ESCALATION_ONCOLOGY_FLAG", "true")
    encounter = clean_encounter.model_copy(
        update={"clinical_notes": "Patient with cancer, tumor identified. Oncology consult."},
    )
    result = check_escalation(encounter, confidence=0.95, estimated_charges=100.0)
    assert result is not None
    assert any("oncology" in r.lower() or "notes" in r.lower() for r in result.reasons)


def test_escalation_incomplete_data_no_notes(clean_encounter: Encounter, monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing/empty clinical notes trigger escalation when flag enabled."""
    monkeypatch.setenv("ESCALATION_INCOMPLETE_DATA_FLAG", "true")
    encounter = clean_encounter.model_copy(update={"clinical_notes": ""})
    result = check_escalation(encounter, confidence=0.95, estimated_charges=100.0)
    assert result is not None
    assert any("clinical" in r.lower() or "notes" in r.lower() for r in result.reasons)


def test_escalation_incomplete_data_no_documents(clean_encounter: Encounter, monkeypatch: pytest.MonkeyPatch) -> None:
    """Empty documents list triggers escalation when flag enabled."""
    monkeypatch.setenv("ESCALATION_INCOMPLETE_DATA_FLAG", "true")
    encounter = clean_encounter.model_copy(update={"documents": []})
    result = check_escalation(encounter, confidence=0.95, estimated_charges=100.0)
    assert result is not None
    assert any("document" in r.lower() for r in result.reasons)


def test_escalation_multiple_reasons(clean_encounter: Encounter, monkeypatch: pytest.MonkeyPatch) -> None:
    """Multiple conditions combine into one EscalationOutput."""
    monkeypatch.setenv("ESCALATION_CONFIDENCE_THRESHOLD", "0.85")
    monkeypatch.setenv("ESCALATION_HIGH_VALUE_THRESHOLD", "100")
    result = check_escalation(
        clean_encounter,
        confidence=0.5,
        estimated_charges=5000.0,
    )
    assert result is not None
    assert len(result.reasons) >= 2
    assert result.message.startswith("Human review required")
