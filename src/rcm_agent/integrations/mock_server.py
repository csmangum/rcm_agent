"""FastAPI mock server implementing eligibility, prior-auth, and claims interfaces over HTTP.

Run with: uvicorn rcm_agent.integrations.mock_server:app --host 0.0.0.0 --port 8000
Or: rcm-agent serve-mock

All endpoints are async for efficient batch processing.
"""

from typing import Any

from fastapi import FastAPI, Request
from pydantic import BaseModel

from rcm_agent.integrations.claims_mock import ClaimsMock
from rcm_agent.integrations.eligibility_mock import EligibilityMock
from rcm_agent.integrations.prior_auth_mock import PriorAuthMock
from rcm_agent.observability.logging import get_logger

logger = get_logger(__name__)

app = FastAPI(
    title="RCM Mock API",
    description="Mock eligibility, prior-auth, and claims endpoints for testing without a real payer.",
    version="0.3.0",
)

_eligibility = EligibilityMock()
_prior_auth = PriorAuthMock()
_claims = ClaimsMock()


@app.middleware("http")
async def log_requests(request: Request, call_next):  # type: ignore[no-untyped-def]
    """Log every request with method and path."""
    logger.info("Mock server request", method=request.method, path=request.url.path)
    response = await call_next(request)
    logger.info(
        "Mock server response",
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
    )
    return response


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check for readiness probes."""
    return {"status": "ok"}


class EligibilityCheckBody(BaseModel):
    payer: str
    member_id: str
    date_of_service: str


class EligibilityVerifyBody(BaseModel):
    payer: str
    member_id: str
    procedure_codes: list[str]


# --- Eligibility ---


@app.post("/eligibility/check")
async def eligibility_check(body: EligibilityCheckBody) -> dict[str, Any]:
    """Check member eligibility. POST JSON: { payer, member_id, date_of_service }."""
    return _eligibility.check_member_eligibility(body.payer, body.member_id, body.date_of_service)


@app.post("/eligibility/verify")
async def eligibility_verify(body: EligibilityVerifyBody) -> dict[str, Any]:
    """Verify benefits for procedure codes. POST JSON: { payer, member_id, procedure_codes }."""
    return _eligibility.verify_benefits(body.payer, body.member_id, body.procedure_codes)


# --- Prior auth ---


@app.post("/prior-auth/submit")
async def prior_auth_submit(auth_packet: dict[str, Any]) -> dict[str, Any]:
    """Submit a prior authorization request. Body: full auth_packet dict."""
    return _prior_auth.submit_auth_request(auth_packet)


@app.get("/prior-auth/status/{auth_id}")
async def prior_auth_status(auth_id: str) -> dict[str, Any]:
    """Get status of a prior authorization by auth_id."""
    return _prior_auth.poll_auth_status(auth_id)


# --- Claims ---


@app.post("/claims/scrub")
async def claims_scrub(claim_payload: dict[str, Any]) -> dict[str, Any]:
    """Scrub a claim for pre-submission edits. Body: full claim payload dict."""
    return _claims.scrub_claim(claim_payload)


@app.post("/claims/submit")
async def claims_submit(claim_payload: dict[str, Any]) -> dict[str, Any]:
    """Submit a claim. Body: full claim payload dict."""
    return _claims.submit_claim(claim_payload)


@app.get("/claims/remit/{claim_id}")
async def claims_remit(claim_id: str) -> dict[str, Any]:
    """Get remittance (835) for a claim by claim_id."""
    return _claims.get_remit(claim_id)
