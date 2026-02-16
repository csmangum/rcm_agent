"""Unit tests for coding and charge capture tools."""

import pytest

from rcm_agent.models import Encounter, EncounterType, Patient, Insurance, ProcedureCode, DiagnosisCode
from rcm_agent.tools.coding import (
    calculate_expected_reimbursement,
    identify_missing_charges,
    search_coding_guidelines,
    suggest_codes,
    validate_code_combinations,
)


def test_suggest_codes_upper_respiratory():
    notes = "Established patient presents with 3 days of rhinorrhea, mild sore throat. Acute upper respiratory infection."
    r = suggest_codes(notes, EncounterType.office_visit, None)
    assert r["confidence"] >= 0.5
    assert "icd_codes" in r and "cpt_codes" in r
    assert len(r["icd_codes"]) >= 1 or len(r["cpt_codes"]) >= 1


def test_suggest_codes_knee_pain():
    notes = "Chronic right knee pain, MRI ordered for meniscal tear."
    r = suggest_codes(notes, "outpatient_procedure", None)
    assert ("M25.561" in [c["code"] for c in r["icd_codes"]] or
            "73721" in r["cpt_codes"] or
            "29881" in r["cpt_codes"]) or (r["icd_codes"] or r["cpt_codes"])


def test_suggest_codes_no_match():
    r = suggest_codes("Random text xyz unknown", EncounterType.office_visit, None)
    assert r["confidence"] == 0.5
    assert "manual review" in r.get("message", "").lower() or (r["icd_codes"] == [] and r["cpt_codes"] == [])


def test_validate_code_combinations_valid():
    r = validate_code_combinations(["M25.561"], ["73721"])
    assert "valid" in r
    assert r["invalid_pairs"] == [] or r["valid"] is True


def test_validate_code_combinations_ncci_bundle():
    r = validate_code_combinations([], ["73721", "73720"])
    assert "invalid_pairs" in r or "modifier_suggestions" in r


def test_validate_code_combinations_modifier_suggestion():
    r = validate_code_combinations([], ["27130", "99223"])
    assert "57" in str(r.get("modifier_suggestions", []))


def test_identify_missing_charges():
    encounter = Encounter(
        encounter_id="ENC-TEST",
        patient=Patient(age=45, gender="F", zip="10001"),
        insurance=Insurance(payer="Aetna", member_id="A1", plan_type="PPO"),
        date="2026-02-10",
        type=EncounterType.office_visit,
        procedures=[ProcedureCode(code="99213", description="Office visit")],
        diagnoses=[DiagnosisCode(code="J06.9", description="URI")],
        clinical_notes="URI",
        documents=[],
    )
    suggested = {"icd_codes": [{"code": "J06.9"}], "cpt_codes": ["99213"]}
    r = identify_missing_charges(encounter, suggested)
    assert "documented_procedures" in r
    assert "suggested_cpts" in r
    assert "missing_charge_flags" in r


def test_search_coding_guidelines_e_and_m():
    r = search_coding_guidelines("e&m")
    assert len(r) >= 1
    assert any("time" in s.lower() or "MDM" in s for s in r)


def test_search_coding_guidelines_unknown():
    r = search_coding_guidelines("nonexistent topic")
    assert len(r) >= 1
    assert "guideline" in r[0].lower() or "CPT" in r[0] or "refer" in r[0].lower()


def test_calculate_expected_reimbursement():
    r = calculate_expected_reimbursement(["99213", "73721"], "Aetna")
    assert r["payer"] == "Aetna"
    assert len(r["per_code"]) == 2
    assert r["total_expected"] >= 0
    assert r["per_code"][0]["cpt_code"] == "99213"


def test_calculate_expected_reimbursement_unknown_payer():
    r = calculate_expected_reimbursement(["99213"], "UnknownPayer")
    assert r["total_expected"] >= 0
    assert r["per_code"][0]["expected_amount"] >= 0
