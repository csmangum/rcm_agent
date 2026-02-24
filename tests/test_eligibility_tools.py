"""Unit tests for eligibility verification tools."""

from rcm_agent.models import Insurance, Patient
from rcm_agent.tools.eligibility import (
    check_coordination_of_benefits,
    check_member_eligibility,
    flag_coverage_gaps,
    verify_benefits,
)


def test_check_member_eligibility_aetna_active():
    r = check_member_eligibility("Aetna", "AET123456789", "2026-02-10")
    assert r["eligible"] is True
    assert "PPO" in r["plan_name"] or "Aetna" in r["plan_name"]
    assert r["member_status"] == "active"
    assert r["termination_date"] is None


def test_check_member_eligibility_anthem_lapsed():
    r = check_member_eligibility("Anthem", "ANT777888999", "2026-02-14")
    assert r["eligible"] is False
    assert r["member_status"] == "terminated"
    assert r["termination_date"] == "2026-01-31"


def test_check_member_eligibility_unknown_default():
    r = check_member_eligibility("UnknownPayer", "UNK111", "2026-01-01")
    assert r["eligible"] is True
    assert r["date_of_service"] == "2026-01-01"


def test_verify_benefits_aetna_99213():
    r = verify_benefits("Aetna", "AET123456789", ["99213"])
    assert len(r["procedures"]) == 1
    assert r["procedures"][0]["procedure_code"] == "99213"
    assert r["procedures"][0]["covered"] is True
    assert r["procedures"][0]["copay"] == 25


def test_verify_benefits_anthem_99285_not_covered():
    r = verify_benefits("Anthem", "ANT777888999", ["99285"])
    assert r["procedures"][0]["covered"] is False


def test_verify_benefits_unknown_procedure_default():
    r = verify_benefits("Aetna", "AET123456789", ["99999"])
    assert len(r["procedures"]) == 1
    assert r["procedures"][0]["covered"] is True
    assert "deductible_remaining" in r["procedures"][0]


def test_check_coordination_of_benefits_under_65():
    patient = Patient(age=45, gender="F", zip="10001")
    insurance = Insurance(payer="Aetna", member_id="AET123", plan_type="PPO")
    r = check_coordination_of_benefits(patient, insurance)
    assert r["has_secondary"] is False


def test_check_coordination_of_benefits_65_plus_non_medicare():
    patient = Patient(age=72, gender="F", zip="60601")
    insurance = Insurance(payer="Blue Cross Blue Shield", member_id="BCBS555", plan_type="PPO")
    r = check_coordination_of_benefits(patient, insurance)
    assert r["has_secondary"] is True
    assert "Medicare" in (r["secondary_note"] or "")


def test_flag_coverage_gaps_eligible_no_gaps():
    elig = {"eligible": True, "member_status": "active", "termination_date": None, "in_network": True}
    gaps = flag_coverage_gaps(elig)
    assert gaps == []


def test_flag_coverage_gaps_terminated():
    elig = {"eligible": False, "member_status": "terminated", "termination_date": "2026-01-31", "in_network": True}
    gaps = flag_coverage_gaps(elig)
    assert any("terminated" in g.lower() for g in gaps)
    assert any("2026-01-31" in g for g in gaps)


def test_flag_coverage_gaps_out_of_network():
    elig = {"eligible": True, "member_status": "active", "termination_date": None, "in_network": False}
    gaps = flag_coverage_gaps(elig)
    assert any("out-of-network" in g.lower() or "network" in g.lower() for g in gaps)
