"""Eligibility verification tools: delegate to backend, plus COB and gap detection."""

from typing import Any

from rcm_agent.integrations.registry import get_eligibility_backend
from rcm_agent.models import Insurance, Patient


def check_member_eligibility(
    payer: str,
    member_id: str,
    date_of_service: str,
) -> dict[str, Any]:
    """Return eligibility status, plan details, effective/term dates from backend."""
    return get_eligibility_backend().check_member_eligibility(
        payer, member_id, date_of_service
    )


def verify_benefits(
    payer: str,
    member_id: str,
    procedure_codes: list[str],
) -> dict[str, Any]:
    """Return covered/not covered, copay, coinsurance, deductible per procedure from backend."""
    return get_eligibility_backend().verify_benefits(
        payer, member_id, procedure_codes
    )


def check_coordination_of_benefits(patient: Patient, insurance: Insurance) -> dict[str, Any]:
    """
    Detect secondary insurance. Mock: flag Medicare secondary when patient age >= 65.
    """
    has_secondary = patient.age >= 65 and "Medicare" not in (insurance.plan_type or "")
    return {
        "has_secondary": has_secondary,
        "secondary_note": "Medicare may be secondary; verify COB order." if has_secondary else None,
        "payer": insurance.payer,
        "plan_type": insurance.plan_type,
    }


def flag_coverage_gaps(eligibility_result: dict[str, Any]) -> list[str]:
    """
    Identify inactive policies, terminated coverage, out-of-network from eligibility result.
    Returns one consolidated message per root cause (no duplicate termination/eligible messages).
    """
    gaps: list[str] = []
    if not eligibility_result.get("eligible", True):
        term_date = eligibility_result.get("termination_date")
        status = eligibility_result.get("member_status", "")
        if status == "terminated" or term_date:
            msg = "Member not eligible: coverage terminated."
            if term_date:
                msg += f" Termination date: {term_date}."
            gaps.append(msg)
        else:
            gaps.append("Member not eligible for coverage on date of service.")
    if eligibility_result.get("in_network") is False:
        gaps.append("Provider or facility may be out-of-network.")
    return gaps
