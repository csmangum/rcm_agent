"""Stub implementation of PriorAuthBackend for testing and development."""

from typing import Any


def _stub_response(operation: str) -> dict[str, Any]:
    return {
        "stub": True,
        "operation": operation,
        "message": "Prior auth backend not implemented; use a real adapter when available.",
    }


class PriorAuthStub:
    """Placeholder implementation of PriorAuthBackend. Returns stub responses only."""

    def submit_auth_request(self, auth_packet: dict[str, Any]) -> dict[str, Any]:
        out = _stub_response("submit_auth_request")
        out["auth_id"] = "STUB-AUTH-ID"
        out["status"] = "stub"
        out["submitted_at"] = "2020-01-01T00:00:00Z"
        return out

    def poll_auth_status(self, auth_id: str) -> dict[str, Any]:
        out = _stub_response("poll_auth_status")
        out["auth_id"] = auth_id
        out["status"] = "stub"
        out["decision"] = None
        out["decision_date"] = None
        return out
