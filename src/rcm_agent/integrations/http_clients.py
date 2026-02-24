"""HTTP client implementations of EligibilityBackend and PriorAuthBackend.

Call the FastAPI mock server (or any compatible API) for the real HTTP client path.
Set ELIGIBILITY_BACKEND=http and PRIOR_AUTH_BACKEND=http with RCM_MOCK_SERVER_URL.
"""

from typing import Any

import httpx

from rcm_agent.integrations.protocols import EligibilityBackend, PriorAuthBackend


class EligibilityHttpClient:
    """EligibilityBackend that calls /eligibility/check and /eligibility/verify over HTTP."""

    def __init__(self, base_url: str, client: httpx.Client | None = None) -> None:
        self._base = base_url.rstrip("/")
        self._client = client

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        url = f"{self._base}{path}"
        if self._client is not None:
            resp = self._client.post(url, json=body)
        else:
            with httpx.Client(timeout=30.0) as c:
                resp = c.post(url, json=body)
        resp.raise_for_status()
        return resp.json()

    def check_member_eligibility(
        self,
        payer: str,
        member_id: str,
        date_of_service: str,
    ) -> dict[str, Any]:
        return self._post(
            "/eligibility/check",
            {"payer": payer, "member_id": member_id, "date_of_service": date_of_service},
        )

    def verify_benefits(
        self,
        payer: str,
        member_id: str,
        procedure_codes: list[str],
    ) -> dict[str, Any]:
        return self._post(
            "/eligibility/verify",
            {"payer": payer, "member_id": member_id, "procedure_codes": procedure_codes},
        )


class PriorAuthHttpClient:
    """PriorAuthBackend that calls /prior-auth/submit and /prior-auth/status/{id} over HTTP."""

    def __init__(self, base_url: str, client: httpx.Client | None = None) -> None:
        self._base = base_url.rstrip("/")
        self._client = client

    def _get(self, path: str) -> dict[str, Any]:
        url = f"{self._base}{path}"
        if self._client is not None:
            resp = self._client.get(url)
        else:
            with httpx.Client(timeout=30.0) as c:
                resp = c.get(url)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        url = f"{self._base}{path}"
        if self._client is not None:
            resp = self._client.post(url, json=body)
        else:
            with httpx.Client(timeout=30.0) as c:
                resp = c.post(url, json=body)
        resp.raise_for_status()
        return resp.json()

    def submit_auth_request(self, auth_packet: dict[str, Any]) -> dict[str, Any]:
        return self._post("/prior-auth/submit", auth_packet)

    def poll_auth_status(self, auth_id: str) -> dict[str, Any]:
        return self._get(f"/prior-auth/status/{auth_id}")
