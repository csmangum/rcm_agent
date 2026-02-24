"""Tests for async HTTP clients against the mock server."""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from rcm_agent.integrations.async_http_clients import (
    AsyncClaimsHttpClient,
    AsyncEligibilityHttpClient,
    AsyncPriorAuthHttpClient,
)
from rcm_agent.integrations.mock_server import app


@pytest.fixture
def async_transport():
    return ASGITransport(app=app)


@pytest_asyncio.fixture
async def async_httpx_client(async_transport):
    async with AsyncClient(transport=async_transport, base_url="http://testserver") as client:
        yield client


@pytest.mark.asyncio
async def test_async_eligibility_check(async_httpx_client):
    client = AsyncEligibilityHttpClient("http://testserver", client=async_httpx_client)
    result = await client.check_member_eligibility("Aetna", "M001", "2026-02-10")
    assert "eligible" in result or "status" in result


@pytest.mark.asyncio
async def test_async_eligibility_verify(async_httpx_client):
    client = AsyncEligibilityHttpClient("http://testserver", client=async_httpx_client)
    result = await client.verify_benefits("Aetna", "M001", ["99213"])
    assert isinstance(result, dict)


@pytest.mark.asyncio
async def test_async_prior_auth_submit(async_httpx_client):
    client = AsyncPriorAuthHttpClient("http://testserver", client=async_httpx_client)
    result = await client.submit_auth_request(
        {
            "encounter_id": "ENC-ASYNC-001",
            "procedure_codes": ["73721"],
            "clinical_justification": "Knee pain",
            "payer": "Aetna",
        }
    )
    assert "auth_id" in result or "status" in result


@pytest.mark.asyncio
async def test_async_claims_scrub(async_httpx_client):
    client = AsyncClaimsHttpClient("http://testserver", client=async_httpx_client)
    result = await client.scrub_claim(
        {
            "payer": "Aetna",
            "member_id": "M001",
            "cpt_codes": ["99213"],
            "icd_codes": ["J06.9"],
            "total_charges": 150.0,
        }
    )
    assert isinstance(result, dict)


@pytest.mark.asyncio
async def test_async_claims_submit(async_httpx_client):
    client = AsyncClaimsHttpClient("http://testserver", client=async_httpx_client)
    result = await client.submit_claim(
        {
            "payer": "Aetna",
            "member_id": "M001",
            "cpt_codes": ["99213"],
            "icd_codes": ["J06.9"],
            "total_charges": 150.0,
        }
    )
    assert "claim_id" in result or "status" in result
