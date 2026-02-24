"""Async HTTP client implementations for batch processing and concurrent calls.

Drop-in async equivalents of the sync HTTP clients in ``http_clients.py``.
"""

from __future__ import annotations

from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from rcm_agent.exceptions import BackendError
from rcm_agent.observability.logging import get_logger

logger = get_logger(__name__)

_RETRYABLE_HTTP_ERRORS = (
    httpx.ConnectError,
    httpx.ReadTimeout,
    httpx.WriteTimeout,
    httpx.PoolTimeout,
    httpx.ConnectTimeout,
)


def _retry_decorator():  # type: ignore[no-untyped-def]
    return retry(
        retry=retry_if_exception_type(_RETRYABLE_HTTP_ERRORS),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
        reraise=True,
    )


class _AsyncBaseHttpClient:
    """Base class for async HTTP clients with shared GET and POST helpers."""

    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None) -> None:
        self._base = base_url.rstrip("/")
        self._client = client

    async def _get(self, path: str) -> dict[str, Any]:
        return await self._request("GET", path)

    async def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", path, body=body)

    @_retry_decorator()
    async def _request(self, method: str, path: str, *, body: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self._base}{path}"
        logger.info("Async HTTP request", method=method, url=url)
        try:
            if self._client is not None:
                resp = await self._client.request(method, url, json=body)
            else:
                async with httpx.AsyncClient(timeout=30.0) as c:
                    resp = await c.request(method, url, json=body)
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


class AsyncEligibilityHttpClient(_AsyncBaseHttpClient):
    """Async EligibilityBackend over HTTP."""

    async def check_member_eligibility(
        self,
        payer: str,
        member_id: str,
        date_of_service: str,
    ) -> dict[str, Any]:
        return await self._post(
            "/eligibility/check",
            {"payer": payer, "member_id": member_id, "date_of_service": date_of_service},
        )

    async def verify_benefits(
        self,
        payer: str,
        member_id: str,
        procedure_codes: list[str],
    ) -> dict[str, Any]:
        return await self._post(
            "/eligibility/verify",
            {"payer": payer, "member_id": member_id, "procedure_codes": procedure_codes},
        )


class AsyncPriorAuthHttpClient(_AsyncBaseHttpClient):
    """Async PriorAuthBackend over HTTP."""

    async def submit_auth_request(self, auth_packet: dict[str, Any]) -> dict[str, Any]:
        return await self._post("/prior-auth/submit", auth_packet)

    async def poll_auth_status(self, auth_id: str) -> dict[str, Any]:
        return await self._get(f"/prior-auth/status/{auth_id}")


class AsyncClaimsHttpClient(_AsyncBaseHttpClient):
    """Async ClaimsBackend over HTTP."""

    async def scrub_claim(self, claim_payload: dict[str, Any]) -> dict[str, Any]:
        return await self._post("/claims/scrub", claim_payload)

    async def submit_claim(self, claim_payload: dict[str, Any]) -> dict[str, Any]:
        return await self._post("/claims/submit", claim_payload)

    async def get_remit(self, claim_id: str) -> dict[str, Any]:
        return await self._get(f"/claims/remit/{claim_id}")
