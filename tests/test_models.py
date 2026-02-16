"""Unit tests for domain models."""

import json
from pathlib import Path

import pytest

from rcm_agent.models import (
    ClaimStatus,
    ClaimSubmission,
    DiagnosisCode,
    Encounter,
    EncounterOutput,
    EncounterStatus,
    EncounterType,
    EscalationOutput,
    Insurance,
    Patient,
    PriorAuthDecision,
    PriorAuthRequest,
    PriorAuthStatus,
    ProcedureCode,
    RcmStage,
)


def test_all_synthetic_encounters_validate(examples_dir: Path) -> None:
    """All 5 synthetic encounter JSON files parse into Encounter."""
    examples = list(examples_dir.glob("encounter_*.json"))
    assert len(examples) >= 5
    for path in examples:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        encounter = Encounter.model_validate(data)
        assert encounter.encounter_id
        assert encounter.patient.age >= 0
        assert encounter.insurance.payer
        assert encounter.date
        assert encounter.type in EncounterType
        assert len(encounter.procedures) >= 1
        assert len(encounter.diagnoses) >= 1


def test_encounter_type_enum_values() -> None:
    """EncounterType has expected values."""
    assert EncounterType.office_visit.value == "office_visit"
    assert EncounterType.outpatient_procedure.value == "outpatient_procedure"
    assert EncounterType.inpatient.value == "inpatient"
    assert EncounterType.emergency.value == "emergency"


def test_rcm_stage_enum_values() -> None:
    """RcmStage has expected values."""
    assert RcmStage.ELIGIBILITY_VERIFICATION.value == "ELIGIBILITY_VERIFICATION"
    assert RcmStage.PRIOR_AUTHORIZATION.value == "PRIOR_AUTHORIZATION"
    assert RcmStage.CODING_CHARGE_CAPTURE.value == "CODING_CHARGE_CAPTURE"
    assert RcmStage.CLAIMS_SUBMISSION.value == "CLAIMS_SUBMISSION"
    assert RcmStage.DENIAL_APPEAL.value == "DENIAL_APPEAL"
    assert RcmStage.HUMAN_ESCALATION.value == "HUMAN_ESCALATION"


def test_encounter_status_enum_values() -> None:
    """EncounterStatus has expected values."""
    assert EncounterStatus.PENDING.value == "PENDING"
    assert EncounterStatus.ESCALATED.value == "ESCALATED"
    assert EncounterStatus.CODED.value == "CODED"


def test_encounter_output_construction() -> None:
    """EncounterOutput can be constructed and serialized."""
    out = EncounterOutput(
        encounter_id="ENC-001",
        stage=RcmStage.CODING_CHARGE_CAPTURE,
        status=EncounterStatus.CODED,
        actions_taken=["code_suggest", "validate"],
        artifacts=["coded_encounter.json"],
        message="Done",
        raw_result={"confidence": 0.9},
    )
    assert out.encounter_id == "ENC-001"
    assert out.stage == RcmStage.CODING_CHARGE_CAPTURE
    assert out.status == EncounterStatus.CODED
    dumped = out.model_dump()
    assert dumped["encounter_id"] == "ENC-001"
    assert EncounterOutput.model_validate(dumped).encounter_id == out.encounter_id


def test_prior_auth_request_construction() -> None:
    """PriorAuthRequest can be constructed and round-trips."""
    req = PriorAuthRequest(
        auth_id="AUTH-1",
        encounter_id="ENC-002",
        payer="UHC",
        procedure_codes=["73721"],
        clinical_justification="Knee pain, failed PT.",
        status=PriorAuthStatus.APPROVED,
        submitted_at="2026-02-10T12:00:00Z",
        decision=PriorAuthDecision.APPROVED,
        decision_date="2026-02-12",
    )
    assert req.auth_id == "AUTH-1"
    assert req.decision == PriorAuthDecision.APPROVED
    again = PriorAuthRequest.model_validate(req.model_dump())
    assert again.auth_id == req.auth_id


def test_claim_submission_construction() -> None:
    """ClaimSubmission can be constructed and round-trips."""
    claim = ClaimSubmission(
        claim_id="CLM-1",
        encounter_id="ENC-001",
        payer="Aetna",
        total_charges=150.0,
        icd_codes=["J06.9"],
        cpt_codes=["99213"],
        modifiers=[],
        status=ClaimStatus.SUBMITTED,
        submitted_at="2026-02-11T00:00:00Z",
    )
    assert claim.claim_id == "CLM-1"
    assert claim.total_charges == 150.0
    again = ClaimSubmission.model_validate(claim.model_dump())
    assert again.claim_id == claim.claim_id


def test_escalation_output_construction() -> None:
    """EscalationOutput can be constructed."""
    out = EscalationOutput(
        encounter_id="ENC-003",
        reasons=["high_dollar", "oncology"],
        stage=RcmStage.HUMAN_ESCALATION,
        status=EncounterStatus.ESCALATED,
        message="Requires review",
    )
    assert out.encounter_id == "ENC-003"
    assert "high_dollar" in out.reasons


def test_encounter_round_trip(sample_encounter_json: dict) -> None:
    """Encounter model_dump / model_validate round-trip."""
    encounter = Encounter.model_validate(sample_encounter_json)
    dumped = encounter.model_dump()
    # Pydantic may serialize EncounterType as enum value
    assert dumped["encounter_id"] == sample_encounter_json["encounter_id"]
    restored = Encounter.model_validate(dumped)
    assert restored.encounter_id == encounter.encounter_id
    assert restored.patient.age == encounter.patient.age


def test_patient_insurance_procedure_diagnosis_models() -> None:
    """Nested models validate and round-trip."""
    patient = Patient(age=45, gender="F", zip="10001")
    assert patient.model_dump()["age"] == 45
    insurance = Insurance(payer="Aetna", member_id="X", plan_type="PPO")
    assert insurance.payer == "Aetna"
    proc = ProcedureCode(code="99213", description="Office visit")
    assert proc.code == "99213"
    diag = DiagnosisCode(code="J06.9", description="URI")
    assert diag.code == "J06.9"
