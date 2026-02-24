"""Stub implementation of EligibilityBackend for testing and development."""

from typing import Any


def _stub_response(operation: str) -> dict[str, Any]:
    return {
        "stub": True,
        "operation": operation,
        "message": "Eligibility backend not implemented; use a real adapter when available.",
    }


class EligibilityStub:
    """Placeholder implementation of EligibilityBackend. Returns stub responses only."""

    def check_member_eligibility(
        self,
        payer: str,
        member_id: str,
        date_of_service: str,
    ) -> dict[str, Any]:
        out = _stub_response("check_member_eligibility")
        out["eligible"] = True
        out["plan_name"] = "Stub Plan"
        out["effective_date"] = "2020-01-01"
        out["termination_date"] = None
        out["in_network"] = True
        out["member_status"] = "stub"
        out["date_of_service"] = date_of_service
        return out

    def verify_benefits(
        self,
        payer: str,
        member_id: str,
        procedure_codes: list[str],
    ) -> dict[str, Any]:
        out = _stub_response("verify_benefits")
        out["payer"] = payer
        out["member_id"] = member_id
        out["procedures"] = [
            {
                "procedure_code": code,
                "covered": True,
                "copay": 0,
                "coinsurance_pct": 0,
                "deductible_remaining": 0,
            }
            for code in procedure_codes
        ]
        return out
