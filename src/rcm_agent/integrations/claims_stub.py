"""Stub implementation of ClaimsBackend for future coding/claims integration."""

from typing import Any

from rcm_agent.integrations._stub_utils import stub_response


_STUB_MESSAGE = "Claims backend not implemented; use a real adapter when available."


class ClaimsStub:
    """Placeholder implementation of ClaimsBackend. Returns stub responses only."""

    def submit_claim(self, claim_payload: dict[str, Any]) -> dict[str, Any]:
        out = stub_response("submit_claim", _STUB_MESSAGE)
        out["claim_id"] = None
        out["status"] = "stub"
        return out

    def get_remit(self, claim_id: str) -> dict[str, Any]:
        out = stub_response("get_remit", _STUB_MESSAGE)
        out["claim_id"] = claim_id
        out["payment"] = None
        out["adjustments"] = []
        return out
