"""Stub implementation of ClaimsBackend for future coding/claims integration."""

from typing import Any


def _stub_response(operation: str) -> dict[str, Any]:
    return {
        "stub": True,
        "operation": operation,
        "message": "Claims backend not implemented; use a real adapter when available.",
    }


class ClaimsStub:
    """Placeholder implementation of ClaimsBackend. Returns stub responses only."""

    def submit_claim(self, claim_payload: dict[str, Any]) -> dict[str, Any]:
        out = _stub_response("submit_claim")
        out["claim_id"] = None
        out["status"] = "stub"
        return out

    def get_remit(self, claim_id: str) -> dict[str, Any]:
        out = _stub_response("get_remit")
        out["claim_id"] = claim_id
        out["payment"] = None
        out["adjustments"] = []
        return out
