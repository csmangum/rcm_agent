"""Shared retry logic for HTTP clients."""

from __future__ import annotations

import httpx
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from rcm_agent.exceptions import BackendError

_RETRYABLE_HTTP_ERRORS = (
    httpx.ConnectError,
    httpx.ReadTimeout,
    httpx.WriteTimeout,
    httpx.PoolTimeout,
    httpx.ConnectTimeout,
)


_RETRYABLE_STATUS_CODES = {502, 503, 504}


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, _RETRYABLE_HTTP_ERRORS):
        return True
    return isinstance(exc, BackendError) and exc.status_code in _RETRYABLE_STATUS_CODES


def _retry_decorator():  # type: ignore[no-untyped-def]
    return retry(
        retry=retry_if_exception(_is_retryable),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
        reraise=True,
    )
