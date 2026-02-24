"""Stub implementation of ClaimsBackend. Returns placeholder responses only."""

from typing import Any

from rcm_agent.integrations._stub_utils import stub_response

_STUB_MESSAGE = "Claims backend not implemented; use a real adapter when available."


class ClaimsStub:
    """Placeholder implementation of ClaimsBackend. Returns stub responses only."""

    def scrub_claim(self, claim_payload: dict[str, Any]) -> dict[str, Any]:
        out = stub_response("scrub_claim", _STUB_MESSAGE)
        out["clean"] = True
        out["errors"] = []
        out["warnings"] = []
        out["edit_actions"] = []
        return out

    def submit_claim(self, claim_payload: dict[str, Any]) -> dict[str, Any]:
        out = stub_response("submit_claim", _STUB_MESSAGE)
        out["claim_id"] = None
        out["status"] = "stub"
        out["submitted_at"] = ""
        out["message"] = _STUB_MESSAGE
        out["tracking_number"] = None
        return out

    def get_remit(self, claim_id: str) -> dict[str, Any]:
        out = stub_response("get_remit", _STUB_MESSAGE)
        out["claim_id"] = claim_id
        out["status"] = "stub"
        out["paid_amount"] = None
        out["allowed_amount"] = None
        out["patient_responsibility"] = None
        out["adjustments"] = []
        out["check_number"] = None
        out["remit_date"] = None
        return out
