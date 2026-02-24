"""Mock implementation of EligibilityBackend with canned payer/member data.

Used as the default backend so crews and CLI behave as before (dict-based responses).
"""

from typing import Any

# Canned eligibility keyed by (payer, member_id). Matches synthetic encounters.
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

_DEFAULT_ELIGIBILITY: dict[str, Any] = {
    "eligible": True,
    "plan_name": "Unknown Plan",
    "effective_date": "2020-01-01",
    "termination_date": None,
    "in_network": True,
    "member_status": "active",
}

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


class EligibilityMock:
    """EligibilityBackend implementation using canned (payer, member_id) data."""

    def check_member_eligibility(
        self,
        payer: str,
        member_id: str,
        date_of_service: str,
    ) -> dict[str, Any]:
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
        self,
        payer: str,
        member_id: str,
        procedure_codes: list[str],
    ) -> dict[str, Any]:
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
