"""Stub implementation of PriorAuthBackend for testing and development."""

from typing import Any

from rcm_agent.integrations._stub_utils import stub_response

_STUB_MESSAGE = "Prior auth backend not implemented; use a real adapter when available."


class PriorAuthStub:
    """Placeholder implementation of PriorAuthBackend. Returns stub responses only."""

    def submit_auth_request(self, auth_packet: dict[str, Any]) -> dict[str, Any]:
        out = stub_response("submit_auth_request", _STUB_MESSAGE)
        out["auth_id"] = "STUB-AUTH-ID"
        out["status"] = "stub"
        out["submitted_at"] = "2020-01-01T00:00:00Z"
        return out

    def poll_auth_status(self, auth_id: str) -> dict[str, Any]:
        out = stub_response("poll_auth_status", _STUB_MESSAGE)
        out["auth_id"] = auth_id
        out["status"] = "stub"
        out["decision"] = None
        out["decision_date"] = None
        return out
