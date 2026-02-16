"""Unit tests for prior authorization tools."""

import pytest

from rcm_agent.models import Encounter, ProcedureCode, DiagnosisCode, Patient, Insurance
from rcm_agent.tools.prior_auth import (
    assemble_auth_packet,
    extract_clinical_indicators,
    poll_auth_status,
    search_payer_policies,
    submit_auth_request,
)


def test_extract_clinical_indicators_knee_mri():
    notes = "Patient with chronic right knee pain, failed conservative therapy including PT and NSAIDs. MRI ordered to evaluate for meniscal tear."
    r = extract_clinical_indicators(notes)
    assert "pain" in r["symptoms"] or "medical_necessity_indicators"
    assert "failed" in r["medical_necessity_indicators"]
    assert "summary" in r


def test_extract_clinical_indicators_empty():
    r = extract_clinical_indicators("")
    assert r["diagnoses"] == []
    assert "summary" in r


def test_search_payer_policies_uhc_mri():
    r = search_payer_policies("UnitedHealthcare", "73721")
    assert len(r) >= 1
    assert any("MRI" in s or "prior auth" in s.lower() for s in r)


def test_search_payer_policies_unknown():
    r = search_payer_policies("UnknownPayer", "99213")
    assert len(r) >= 1
    assert "No specific policy" in r[0] or "policy" in r[0].lower()


def test_assemble_auth_packet():
    encounter = Encounter(
        encounter_id="ENC-TEST",
        patient=Patient(age=58, gender="M", zip="850xx"),
        insurance=Insurance(payer="UHC", member_id="U123", plan_type="PPO"),
        date="2026-02-10",
        type="outpatient_procedure",
        procedures=[ProcedureCode(code="73721", description="MRI knee")],
        diagnoses=[DiagnosisCode(code="M25.561", description="Pain in right knee")],
        clinical_notes="Knee pain, failed PT.",
        documents=[],
    )
    clinical_indicators = extract_clinical_indicators(encounter.clinical_notes)
    policy_matches = {"73721": search_payer_policies("UHC", "73721")}
    packet = assemble_auth_packet(encounter, clinical_indicators, policy_matches)
    assert packet["encounter_id"] == "ENC-TEST"
    assert packet["payer"] == "UHC"
    assert "73721" in packet["procedure_codes"]
    assert "clinical_indicators" in packet
    assert "policy_references" in packet


def test_submit_auth_request():
    packet = {"encounter_id": "ENC-TEST", "payer": "Payer", "procedure_codes": ["73721"]}
    r = submit_auth_request(packet)
    assert "auth_id" in r
    assert r["auth_id"].startswith("AUTH-")
    assert r["status"] == "submitted"
    assert "submitted_at" in r


def test_poll_auth_status_after_submit():
    packet = {"encounter_id": "ENC-POLL", "payer": "P", "procedure_codes": ["73721"]}
    submit_result = submit_auth_request(packet)
    auth_id = submit_result["auth_id"]
    r = poll_auth_status(auth_id)
    assert r["auth_id"] == auth_id
    assert r["status"] == "approved"
    assert r["decision"] == "approved"


def test_poll_auth_status_unknown():
    r = poll_auth_status("AUTH-UNKNOWN99")
    assert r["auth_id"] == "AUTH-UNKNOWN99"
    assert r["status"] == "pending"
    assert r.get("decision") is None or "not found" in r.get("message", "").lower()
