"""HTTP client implementations of EligibilityBackend, PriorAuthBackend, and ClaimsBackend.

Call the FastAPI mock server (or any compatible API) for the real HTTP client path.
Set ELIGIBILITY_BACKEND=http, PRIOR_AUTH_BACKEND=http, CLAIMS_BACKEND=http with RCM_MOCK_SERVER_URL.
"""

from __future__ import annotations

from typing import Any

import httpx

from rcm_agent.exceptions import BackendError
from rcm_agent.integrations._retry_utils import (
    _RETRYABLE_HTTP_ERRORS,
    _retry_decorator,
)
from rcm_agent.observability.logging import get_logger

logger = get_logger(__name__)


class _BaseHttpClient:
    """Base class for HTTP clients with shared GET and POST helpers."""

    def __init__(self, base_url: str, client: httpx.Client | None = None) -> None:
        self._base = base_url.rstrip("/")
        self._client = client

    def _get(self, path: str) -> dict[str, Any]:
        return self._request("GET", path)

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", path, body=body)

    @_retry_decorator()
    def _request(self, method: str, path: str, *, body: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self._base}{path}"
        logger.info("HTTP request", method=method, url=url)
        try:
            if self._client is not None:
                resp = self._client.request(method, url, json=body)
            else:
                with httpx.Client(timeout=30.0) as c:
                    resp = c.request(method, url, json=body)
            resp.raise_for_status()
            result: dict[str, Any] = resp.json()
            return result
        except httpx.HTTPStatusError as exc:
            raise BackendError(
                f"{method} {url} returned {exc.response.status_code}",
                backend=self._base,
                status_code=exc.response.status_code,
            ) from exc
        except _RETRYABLE_HTTP_ERRORS:
            raise


class EligibilityHttpClient(_BaseHttpClient):
    """EligibilityBackend that calls /eligibility/check and /eligibility/verify over HTTP."""

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


class PriorAuthHttpClient(_BaseHttpClient):
    """PriorAuthBackend that calls /prior-auth/submit and /prior-auth/status/{id} over HTTP."""

    def submit_auth_request(self, auth_packet: dict[str, Any]) -> dict[str, Any]:
        return self._post("/prior-auth/submit", auth_packet)

    def poll_auth_status(self, auth_id: str) -> dict[str, Any]:
        return self._get(f"/prior-auth/status/{auth_id}")


class ClaimsHttpClient(_BaseHttpClient):
    """ClaimsBackend that calls /claims/* endpoints over HTTP."""

    def scrub_claim(self, claim_payload: dict[str, Any]) -> dict[str, Any]:
        return self._post("/claims/scrub", claim_payload)

    def submit_claim(self, claim_payload: dict[str, Any]) -> dict[str, Any]:
        return self._post("/claims/submit", claim_payload)

    def get_remit(self, claim_id: str) -> dict[str, Any]:
        return self._get(f"/claims/remit/{claim_id}")
