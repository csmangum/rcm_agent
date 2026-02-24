"""Mock implementation of PriorAuthBackend with in-memory auth store.

Used as the default backend; submit stores the packet and poll returns approved (POC).
"""

import uuid
from datetime import datetime, timezone
from typing import Any


class PriorAuthMock:
    """PriorAuthBackend implementation using an in-memory dict keyed by auth_id."""

    def __init__(self) -> None:
        self._store: dict[str, dict[str, Any]] = {}

    def reset(self) -> None:
        """Clear the auth store (for tests)."""
        self._store.clear()

    def submit_auth_request(self, auth_packet: dict[str, Any]) -> dict[str, Any]:
        auth_id = f"AUTH-{uuid.uuid4().hex[:8].upper()}"
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self._store[auth_id] = {
            "auth_packet": auth_packet,
            "status": "submitted",
            "decision": None,
            "submitted_at": now,
        }
        return {
            "auth_id": auth_id,
            "status": "submitted",
            "submitted_at": now,
            "message": "Prior auth request submitted successfully (mock).",
        }

    def poll_auth_status(self, auth_id: str) -> dict[str, Any]:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if auth_id in self._store:
            record = self._store[auth_id]
            record["status"] = "approved"
            record["decision"] = "approved"
            record["decision_date"] = now
            return {
                "auth_id": auth_id,
                "status": "approved",
                "decision": "approved",
                "decision_date": now,
            }
        return {
            "auth_id": auth_id,
            "status": "pending",
            "decision": None,
            "message": "Auth request not found or still pending (mock).",
        }
