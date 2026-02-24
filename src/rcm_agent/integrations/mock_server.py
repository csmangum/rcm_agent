"""FastAPI mock server implementing eligibility, prior-auth, and claims interfaces over HTTP.

Run with: uvicorn rcm_agent.integrations.mock_server:app --host 0.0.0.0 --port 8000
Or: rcm-agent serve-mock
"""

from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

from rcm_agent.integrations.claims_mock import ClaimsMock
from rcm_agent.integrations.eligibility_mock import EligibilityMock
from rcm_agent.integrations.prior_auth_mock import PriorAuthMock

app = FastAPI(
    title="RCM Mock API",
    description="Mock eligibility, prior-auth, and claims endpoints for testing without a real payer.",
    version="0.2.0",
)

_eligibility = EligibilityMock()
_prior_auth = PriorAuthMock()
_claims = ClaimsMock()


@app.get("/health")
def health() -> dict[str, str]:
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
def eligibility_check(body: EligibilityCheckBody) -> dict[str, Any]:
    """Check member eligibility. POST JSON: { payer, member_id, date_of_service }."""
    return _eligibility.check_member_eligibility(body.payer, body.member_id, body.date_of_service)


@app.post("/eligibility/verify")
def eligibility_verify(body: EligibilityVerifyBody) -> dict[str, Any]:
    """Verify benefits for procedure codes. POST JSON: { payer, member_id, procedure_codes }."""
    return _eligibility.verify_benefits(body.payer, body.member_id, body.procedure_codes)


# --- Prior auth ---


@app.post("/prior-auth/submit")
def prior_auth_submit(auth_packet: dict[str, Any]) -> dict[str, Any]:
    """Submit a prior authorization request. Body: full auth_packet dict."""
    return _prior_auth.submit_auth_request(auth_packet)


@app.get("/prior-auth/status/{auth_id}")
def prior_auth_status(auth_id: str) -> dict[str, Any]:
    """Get status of a prior authorization by auth_id."""
    return _prior_auth.poll_auth_status(auth_id)


# --- Claims ---


@app.post("/claims/scrub")
def claims_scrub(claim_payload: dict[str, Any]) -> dict[str, Any]:
    """Scrub a claim for pre-submission edits. Body: full claim payload dict."""
    return _claims.scrub_claim(claim_payload)


@app.post("/claims/submit")
def claims_submit(claim_payload: dict[str, Any]) -> dict[str, Any]:
    """Submit a claim. Body: full claim payload dict."""
    return _claims.submit_claim(claim_payload)


@app.get("/claims/remit/{claim_id}")
def claims_remit(claim_id: str) -> dict[str, Any]:
    """Get remittance (835) for a claim by claim_id."""
    return _claims.get_remit(claim_id)
