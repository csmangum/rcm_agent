"""FastAPI mock server implementing eligibility and prior-auth interfaces over HTTP.

Run with: uvicorn rcm_agent.integrations.mock_server:app --host 0.0.0.0 --port 8000
Or: rcm-agent serve-mock
"""

from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

from rcm_agent.integrations.eligibility_mock import EligibilityMock
from rcm_agent.integrations.prior_auth_mock import PriorAuthMock

app = FastAPI(
    title="RCM Mock API",
    description="Mock eligibility and prior-auth endpoints for testing without a real payer.",
    version="0.1.0",
)

_eligibility = EligibilityMock()
_prior_auth = PriorAuthMock()


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
