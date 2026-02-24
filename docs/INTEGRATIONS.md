# External Protocols and Integrations

This document describes the RCM Agent’s **external integration layer**: protocols (interfaces), built-in mocks, configuration, and how to plug in real payer/EHR systems (FHIR, EDI, or custom APIs).

## Overview

- **Protocols** live in `rcm_agent.integrations.protocols`: Python `Protocol` types that define the contract for eligibility, prior auth, and (stub) claims.
- **Implementations** are chosen by a **registry** (`rcm_agent.integrations.registry`) using config (environment variables). Crews and tools never import concrete backends; they call `get_eligibility_backend()` and `get_prior_auth_backend()`.
- **Default** is in-memory **mocks** so the app runs and demos without any external systems. You can switch to HTTP (mock server), or add **real** adapters (FHIR, EDI) by implementing the protocols and registering them.

## Protocols (interfaces)

All protocols are in `src/rcm_agent/integrations/protocols.py` and are `@runtime_checkable` so you can use `isinstance(impl, EligibilityBackend)` in tests.

### EligibilityBackend

Used for payer eligibility and benefits checks. Real systems might map to FHIR Coverage/ExplanationOfBenefit or EDI 270/271.

| Method | Purpose |
|--------|---------|
| `check_member_eligibility(payer, member_id, date_of_service)` | Is the member eligible on that date? |
| `verify_benefits(payer, member_id, procedure_codes)` | Per-procedure coverage, copay, coinsurance, deductible. |

**check_member_eligibility** — Returns a dict with at least:

- `eligible`: bool  
- `plan_name`: str  
- `effective_date`: str \| None  
- `termination_date`: str \| None  
- `in_network`: bool  
- `member_status`: str (e.g. `"active"`, `"terminated"`)  
- `date_of_service`: str  

**verify_benefits** — Returns a dict with at least:

- `payer`: str  
- `member_id`: str  
- `procedures`: list of dicts with `procedure_code`, `covered`, `copay`, `coinsurance_pct`, `deductible_remaining`  

Implementations may add extra keys; the agent only relies on the ones above.

### PriorAuthBackend

Used for prior authorization submit and status polling. Real systems might map to FHIR Task/RequestGroup or payer-specific APIs.

| Method | Purpose |
|--------|---------|
| `submit_auth_request(auth_packet)` | Submit a prior auth request. |
| `poll_auth_status(auth_id)` | Get status/decision for a submitted request. |

**submit_auth_request** — `auth_packet` is a dict (encounter_id, patient, payer, member_id, date_of_service, procedure_codes, diagnoses, clinical_justification, etc.). Returns at least:

- `auth_id`: str  
- `status`: str (e.g. `"submitted"`)  
- `submitted_at`: str (ISO datetime)  
- `message`: str (optional)  

**poll_auth_status** — Returns at least:

- `auth_id`: str  
- `status`: str (e.g. `"pending"`, `"approved"`, `"denied"`)  
- `decision`: str \| None (`"approved"`, `"denied"`, or None)  
- `decision_date`: str \| None (ISO datetime when present)  
- `message`: str (optional)  

### ClaimsBackend (stub)

Placeholder for future claims submission and remittance (EDI 837/835 or FHIR Claim/ClaimResponse).

- `submit_claim(claim_payload)` → dict with e.g. `claim_id`, `status`  
- `get_remit(claim_id)` → dict with payment info, adjustments, CARC/RARC, etc.  

The codebase currently uses `ClaimsStub`; real implementations are not wired into the registry yet.

---

## Built-in implementations

### Mock (default)

- **Eligibility**: `EligibilityMock` — Canned responses keyed by `(payer, member_id)`; matches synthetic encounters (Aetna, UHC, BCBS, Cigna, Anthem). Unknown keys get a default “active” response.
- **Prior auth**: `PriorAuthMock` — In-memory store; submit returns an `auth_id`, poll returns `approved` for any known id.

No environment variables are required; crews and CLI work out of the box.

### HTTP (mock server)

- **Eligibility**: `EligibilityHttpClient` — Calls `POST /eligibility/check` and `POST /eligibility/verify` on a base URL.
- **Prior auth**: `PriorAuthHttpClient` — Calls `POST /prior-auth/submit` and `GET /prior-auth/status/{id}`.

Used when you run the FastAPI mock server and point the agent at it (see below). Lets you test the real HTTP path without a real payer.

---

## Configuration

Config is read from the environment (see `rcm_agent.config.get_integrations_config()`).

| Variable | Default | Meaning |
|----------|---------|---------|
| `ELIGIBILITY_BACKEND` | `mock` | Backend name: `mock`, `http`, or a custom name you register. |
| `PRIOR_AUTH_BACKEND` | `mock` | Same for prior auth. |
| `RCM_MOCK_SERVER_URL` | `http://localhost:8000` | Base URL when backend is `http` (no trailing slash). |

Examples:

- Default (no env): both backends use in-memory mocks.  
- `ELIGIBILITY_BACKEND=http` and `PRIOR_AUTH_BACKEND=http`, `RCM_MOCK_SERVER_URL=http://localhost:8000`: tools and crews call the mock API over HTTP.  
- After adding adapters: `ELIGIBILITY_BACKEND=fhir`, `PRIOR_AUTH_BACKEND=fhir` (or `edi`, etc.) to use real systems.

---

## Mock HTTP server

The FastAPI app in `rcm_agent.integrations.mock_server` exposes the same contracts over HTTP for testing and demos.

**Endpoints:**

| Method | Path | Body / params | Purpose |
|--------|------|----------------|----------|
| GET | `/health` | — | Readiness check. |
| POST | `/eligibility/check` | `{ "payer", "member_id", "date_of_service" }` | Same as `EligibilityBackend.check_member_eligibility`. |
| POST | `/eligibility/verify` | `{ "payer", "member_id", "procedure_codes" }` | Same as `EligibilityBackend.verify_benefits`. |
| POST | `/prior-auth/submit` | Full `auth_packet` dict | Same as `PriorAuthBackend.submit_auth_request`. |
| GET | `/prior-auth/status/{auth_id}` | — | Same as `PriorAuthBackend.poll_auth_status`. |

**Run the server:**

```bash
rcm-agent serve-mock
# or
uvicorn rcm_agent.integrations.mock_server:app --host 0.0.0.0 --port 8000
```

**Use it as backend:** set `ELIGIBILITY_BACKEND=http`, `PRIOR_AUTH_BACKEND=http`, and `RCM_MOCK_SERVER_URL` to the server URL (e.g. `http://localhost:8000`). The registry will instantiate the HTTP clients and all eligibility/prior-auth tool calls will go over the wire.

---

## Plugging in a real system

To connect to a real eligibility or prior-auth system (FHIR, EDI, or a custom API):

### 1. Implement the protocol

Create a class that implements the right protocol (same method names and return shapes).

**Example — eligibility adapter calling a FHIR Coverage API:**

```python
# my_adapters/fhir_eligibility.py
from typing import Any

class EligibilityFhir:
    """EligibilityBackend backed by FHIR Coverage / EOB."""

    def __init__(self, fhir_base_url: str, ...):
        self._base = fhir_base_url
        # ...

    def check_member_eligibility(
        self, payer: str, member_id: str, date_of_service: str
    ) -> dict[str, Any]:
        # Call FHIR Coverage search, map to agent shape
        return {
            "eligible": ...,
            "plan_name": ...,
            "effective_date": ...,
            "termination_date": ...,
            "in_network": ...,
            "member_status": ...,
            "date_of_service": date_of_service,
        }

    def verify_benefits(
        self, payer: str, member_id: str, procedure_codes: list[str]
    ) -> dict[str, Any]:
        # Call FHIR EOB or 271, map to agent shape
        return {"payer": payer, "member_id": member_id, "procedures": [...]}
```

Same idea for prior auth: implement `PriorAuthBackend` with `submit_auth_request` and `poll_auth_status`, mapping your API (FHIR Task, EDI, etc.) to the expected request/response dicts.

### 2. Register the backend

The registry is in `src/rcm_agent/integrations/registry.py`. Add your implementation to the backend maps and (if needed) handle a new config value.

**Eligibility:**

```python
# In registry.py
from my_adapters.fhir_eligibility import EligibilityFhir

_ELIGIBILITY_BACKENDS: dict[str, type[EligibilityBackend]] = {
    "mock": EligibilityMock,
    "fhir": EligibilityFhir,  # add this
}
```

If your backend needs constructor args (e.g. base URL, API key), you can read them from config or env inside the registry when instantiating:

```python
if name == "fhir":
    base_url = os.environ.get("FHIR_ELIGIBILITY_URL", "")
    _eligibility_backend = EligibilityFhir(base_url)
```

**Prior auth:** same pattern with `_PRIOR_AUTH_BACKENDS` and `get_prior_auth_backend()`.

### 3. Configure at runtime

Set the appropriate env var so the registry picks your implementation:

```bash
export ELIGIBILITY_BACKEND=fhir
export FHIR_ELIGIBILITY_URL=https://fhir.example.com
# same for PRIOR_AUTH_BACKEND if you add a prior-auth adapter
```

Crew and tool code stays unchanged; they still call `get_eligibility_backend()` and `get_prior_auth_backend()`.

### 4. Optional: dependency injection for tests

For tests you can either:

- Rely on the default `mock` backend, or  
- Set `ELIGIBILITY_BACKEND=mock` / `PRIOR_AUTH_BACKEND=mock` and call `reset_integration_backends()` before tests so the registry re-reads config.

To test with a custom implementation without changing env, you’d need to either inject the backend into the tools (future refactor) or temporarily patch the registry’s cached instance.

---

## File layout

```
src/rcm_agent/integrations/
  protocols.py       # EligibilityBackend, PriorAuthBackend, ClaimsBackend
  registry.py        # get_eligibility_backend(), get_prior_auth_backend(), config wiring
  eligibility_mock.py
  prior_auth_mock.py
  http_clients.py    # EligibilityHttpClient, PriorAuthHttpClient
  mock_server.py     # FastAPI app (serve-mock)
  eligibility_stub.py   # Optional stub for tests
  prior_auth_stub.py
  claims_stub.py
```

Tools that call external systems use the registry only:

- `tools/eligibility.py` → `get_eligibility_backend()`
- `tools/prior_auth.py` → `get_prior_auth_backend()`

No tool or crew imports `EligibilityMock` or `PriorAuthMock` directly.

---

## Summary

| Goal | Action |
|------|--------|
| Run/demo with no external systems | Use defaults (no env); mocks are used. |
| Test HTTP client path | Run `rcm-agent serve-mock`, set `ELIGIBILITY_BACKEND=http`, `PRIOR_AUTH_BACKEND=http`, `RCM_MOCK_SERVER_URL=http://localhost:8000`. |
| Use a real payer/EHR API | Implement the protocol, register it in `registry.py`, set `ELIGIBILITY_BACKEND` / `PRIOR_AUTH_BACKEND` (and any backend-specific env) and run. |
