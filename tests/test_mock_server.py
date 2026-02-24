"""Tests for FastAPI mock server and HTTP client backends."""

import time
from threading import Thread

import pytest
from fastapi.testclient import TestClient

from rcm_agent.integrations.http_clients import EligibilityHttpClient, PriorAuthHttpClient
from rcm_agent.integrations.mock_server import app

# Port for live-server test (real HTTP client path). Must be free.
_LIVE_PORT = 18765


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# --- Server contract (TestClient vs app) ---


def test_eligibility_check_endpoint(client: TestClient) -> None:
    r = client.post(
        "/eligibility/check",
        json={"payer": "Aetna", "member_id": "AET123456789", "date_of_service": "2026-02-10"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["eligible"] is True
    assert "PPO" in data["plan_name"] or "Aetna" in data["plan_name"]
    assert data["member_status"] == "active"
    assert data["date_of_service"] == "2026-02-10"


def test_eligibility_check_anthem_lapsed(client: TestClient) -> None:
    r = client.post(
        "/eligibility/check",
        json={"payer": "Anthem", "member_id": "ANT777888999", "date_of_service": "2026-02-14"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["eligible"] is False
    assert data["member_status"] == "terminated"


def test_eligibility_verify_endpoint(client: TestClient) -> None:
    r = client.post(
        "/eligibility/verify",
        json={"payer": "Aetna", "member_id": "AET123456789", "procedure_codes": ["99213"]},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["payer"] == "Aetna"
    assert len(data["procedures"]) == 1
    assert data["procedures"][0]["procedure_code"] == "99213"
    assert data["procedures"][0]["covered"] is True


def test_prior_auth_submit_endpoint(client: TestClient) -> None:
    r = client.post(
        "/prior-auth/submit",
        json={"encounter_id": "ENC-TEST", "payer": "Payer", "procedure_codes": ["73721"]},
    )
    assert r.status_code == 200
    data = r.json()
    assert "auth_id" in data
    assert data["auth_id"].startswith("AUTH-")
    assert data["status"] == "submitted"
    assert "submitted_at" in data


def test_prior_auth_status_after_submit(client: TestClient) -> None:
    sub = client.post(
        "/prior-auth/submit",
        json={"encounter_id": "ENC-POLL", "payer": "P", "procedure_codes": ["73721"]},
    )
    auth_id = sub.json()["auth_id"]
    r = client.get(f"/prior-auth/status/{auth_id}")
    assert r.status_code == 200
    data = r.json()
    assert data["auth_id"] == auth_id
    assert data["status"] == "approved"
    assert data["decision"] == "approved"


def test_prior_auth_status_unknown(client: TestClient) -> None:
    r = client.get("/prior-auth/status/AUTH-UNKNOWN99")
    assert r.status_code == 200
    data = r.json()
    assert data["auth_id"] == "AUTH-UNKNOWN99"
    assert data["status"] == "pending"
    assert data.get("decision") is None


# --- Real HTTP client path (live server in background) ---


def _run_server() -> None:
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=_LIVE_PORT, log_level="warning")


def _wait_for_server(base_url: str, timeout: float = 5.0) -> bool:
    import urllib.request
    url = f"{base_url}/health"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as r:
                if r.status == 200:
                    return True
        except Exception:
            time.sleep(0.1)
            continue
    return False


@pytest.fixture(scope="module")
def live_server_base() -> str | None:
    """Start mock server once per module; return base URL or None if server didn't start."""
    thread = Thread(target=_run_server, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{_LIVE_PORT}"
    if not _wait_for_server(base):
        return None
    return base


def test_eligibility_http_client_real_request(live_server_base: str | None) -> None:
    """EligibilityHttpClient against a live mock server (real HTTP)."""
    if live_server_base is None:
        pytest.skip(f"Mock server did not start on port {_LIVE_PORT} in time")
    elig = EligibilityHttpClient(live_server_base)
    result = elig.check_member_eligibility("Aetna", "AET123456789", "2026-01-01")
    assert result["eligible"] is True
    assert result["member_status"] == "active"
    benefits = elig.verify_benefits("Aetna", "AET123456789", ["99213"])
    assert benefits["procedures"][0]["covered"] is True
    assert benefits["procedures"][0]["copay"] == 25


def test_prior_auth_http_client_real_request(live_server_base: str | None) -> None:
    """PriorAuthHttpClient against a live mock server (real HTTP)."""
    if live_server_base is None:
        pytest.skip(f"Mock server did not start on port {_LIVE_PORT} in time")
    pa = PriorAuthHttpClient(live_server_base)
    packet = {"encounter_id": "ENC-HTTP", "payer": "P", "procedure_codes": ["73721"]}
    sub = pa.submit_auth_request(packet)
    assert sub["auth_id"].startswith("AUTH-")
    assert sub["status"] == "submitted"
    status = pa.poll_auth_status(sub["auth_id"])
    assert status["status"] == "approved"
    assert status["decision"] == "approved"
