"""Eligibility verification tools: mock payer API and coverage gap detection."""

from typing import Any

from rcm_agent.models import Insurance, Patient


# Canned eligibility responses keyed by (payer, member_id) for synthetic encounters.
# ENC-001 Aetna, ENC-002 UHC, ENC-003 BCBS = active. ENC-004 Cigna = active HMO. ENC-005 Anthem = lapsed.
_MOCK_ELIGIBILITY: dict[tuple[str, str], dict[str, Any]] = {
    ("Aetna", "AET123456789"): {
        "eligible": True,
        "plan_name": "Aetna PPO Standard",
        "effective_date": "2025-01-01",
        "termination_date": None,
        "in_network": True,
        "member_status": "active",
    },
    ("UnitedHealthcare", "UHC987654321"): {
        "eligible": True,
        "plan_name": "UHC PPO Choice",
        "effective_date": "2025-06-01",
        "termination_date": None,
        "in_network": True,
        "member_status": "active",
    },
    ("Blue Cross Blue Shield", "BCBS555111222"): {
        "eligible": True,
        "plan_name": "BCBS Medicare Advantage PPO",
        "effective_date": "2024-01-01",
        "termination_date": None,
        "in_network": True,
        "member_status": "active",
    },
    ("Cigna", "CIG444333222"): {
        "eligible": True,
        "plan_name": "Cigna HMO Local",
        "effective_date": "2025-03-01",
        "termination_date": None,
        "in_network": True,
        "member_status": "active",
    },
    ("Anthem", "ANT777888999"): {
        "eligible": False,
        "plan_name": "Anthem EPO",
        "effective_date": "2025-01-01",
        "termination_date": "2026-01-31",
        "in_network": True,
        "member_status": "terminated",
    },
}

# Default when (payer, member_id) not in mock data.
_DEFAULT_ELIGIBILITY: dict[str, Any] = {
    "eligible": True,
    "plan_name": "Unknown Plan",
    "effective_date": "2020-01-01",
    "termination_date": None,
    "in_network": True,
    "member_status": "active",
}

# Benefits per (payer, member_id) and procedure code. Synthetic encounters only.
_MOCK_BENEFITS: dict[tuple[str, str], dict[str, dict[str, Any]]] = {
    ("Aetna", "AET123456789"): {
        "99213": {"covered": True, "copay": 25, "coinsurance_pct": 0, "deductible_remaining": 0},
    },
    ("UnitedHealthcare", "UHC987654321"): {
        "73721": {"covered": True, "copay": 0, "coinsurance_pct": 20, "deductible_remaining": 200},
    },
    ("Blue Cross Blue Shield", "BCBS555111222"): {
        "27130": {"covered": True, "copay": 0, "coinsurance_pct": 20, "deductible_remaining": 0},
        "99223": {"covered": True, "copay": 0, "coinsurance_pct": 20, "deductible_remaining": 0},
    },
    ("Cigna", "CIG444333222"): {
        "29881": {"covered": True, "copay": 50, "coinsurance_pct": 10, "deductible_remaining": 100},
    },
    ("Anthem", "ANT777888999"): {
        "99285": {"covered": False, "copay": None, "coinsurance_pct": None, "deductible_remaining": None},
    },
}


def check_member_eligibility(
    payer: str,
    member_id: str,
    date_of_service: str,
) -> dict[str, Any]:
    """
    Mock payer API: return eligibility status, plan details, effective/term dates.
    Keyed by (payer, member_id); unknown keys get default active response.
    """
    key = (payer.strip(), member_id.strip())
    result = _MOCK_ELIGIBILITY.get(key, _DEFAULT_ELIGIBILITY.copy())
    return {
        "eligible": result["eligible"],
        "plan_name": result["plan_name"],
        "effective_date": result["effective_date"],
        "termination_date": result["termination_date"],
        "in_network": result["in_network"],
        "member_status": result["member_status"],
        "date_of_service": date_of_service,
    }


def verify_benefits(
    payer: str,
    member_id: str,
    procedure_codes: list[str],
) -> dict[str, Any]:
    """
    Mock benefits check: covered/not covered, copay, coinsurance, deductible remaining per procedure.
    """
    key = (payer.strip(), member_id.strip())
    per_code = _MOCK_BENEFITS.get(key, {})
    procedures: list[dict[str, Any]] = []
    for code in procedure_codes:
        info = per_code.get(code, {
            "covered": True,
            "copay": 0,
            "coinsurance_pct": 20,
            "deductible_remaining": 500,
        })
        procedures.append({"procedure_code": code, **info})
    return {"payer": payer, "member_id": member_id, "procedures": procedures}


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
