# Next Iteration Options for rcm_agent

## Current State Summary

`rcm_agent` is at **v0.1.0** and has completed all 6 phases from `PHASE_PLAN.md`, including the stretch Phase 6 (Denial/Appeal crew). The library currently has:

- 4 fully implemented specialized crews (eligibility, prior auth, coding, denial/appeal)
- A heuristic router with LLM fallback stub
- SQLite persistence with audit trails
- Protocol-based integration layer with mock + HTTP backends
- RAG infrastructure (mock + ChromaDB)
- CLI interface with 6 commands
- 20 test modules covering tools, crews, DB, CLI, integrations, and RAG
- 6 synthetic encounter examples

The foundation is solid. Below are **5 distinct iteration options**, ordered roughly from highest immediate impact to longer-horizon work.

---

## Option 1: Claims Submission Crew (Complete the RCM Cycle)

**Effort:** Medium (1–2 weeks) | **Impact:** High

The `CLAIMS_SUBMISSION` stage is the only RCM stage that still routes to `run_stub_crew`. The `ClaimsBackend` protocol already exists in `protocols.py` but has no real implementation. Completing this closes the full revenue cycle loop.

### What it involves

- Implement `ClaimsSubmissionCrew` with agents: claim_assembler, scrubber, submission_tracker
- Build tools: `assemble_clean_claim()`, `scrub_claim()` (pre-submission edits/validation), `submit_claim()`, `check_remit_status()`
- Add mock + HTTP implementations of the `ClaimsBackend` protocol
- Wire into the router and main crew dispatch
- Generate claim artifacts (837-style JSON, remittance summary)
- Completes the end-to-end flow: intake → eligibility → prior auth → coding → **claim submission** → denial/appeal

### Why this option

It's the most natural next step — the stub is already there, the protocol is defined, and it closes the biggest functional gap. Every other crew feeds into this one.

---

## Option 2: Production Hardening & Observability

**Effort:** Medium (1–2 weeks) | **Impact:** High for real-world use

The codebase works as a POC but has gaps that would matter for any real demonstration or pilot. This iteration focuses on reliability and visibility.

### What it involves

- **Custom exception hierarchy:** `RcmAgentError` base, `BackendError`, `RoutingError`, `ValidationError` — replacing generic `Exception` catches and silent failures (e.g., `update_status` returning silently on missing encounters)
- **Structured logging:** The `observability/` module is empty. Add structured JSON logging with encounter context (encounter_id, stage, action) at key decision points (router classification, escalation decision, crew dispatch, tool calls)
- **DB connection management:** Replace per-operation `connect()`/`close()` with a context manager or connection pool
- **Retry logic:** Use the existing `tenacity` dependency for HTTP backend calls and DB operations
- **DB migrations:** Add a simple migration system so schema changes don't require DB recreation
- **Async support:** The HTTP clients and FastAPI mock server could benefit from async, especially for batch processing

### Why this option

Makes the difference between "it works in a demo" and "it works reliably." The observability gap is the most glaring — there is a `langsmith` optional dependency but zero instrumentation.

---

## Option 3: LLM Router & Intelligent Routing

**Effort:** Small–Medium (3–5 days) | **Impact:** Medium

The router is currently pure heuristics with a disabled LLM fallback. The code has a `pass` placeholder at the LLM path. This iteration makes routing intelligent.

### What it involves

- Implement the LLM-based `RouterCrew` using CrewAI with a classification prompt
- Enable hybrid routing: heuristics first (fast, cheap), LLM fallback when confidence < threshold
- Add **multi-stage routing** — some encounters need more than one crew (e.g., eligibility check *then* prior auth *then* coding). Currently encounters are routed to exactly one crew
- Add router evaluation: compare heuristic vs LLM classifications across synthetic encounters, log disagreements
- Externalize the auth-required CPT list and payer-specific routing rules from hardcoded dicts to config files

### Why this option

Multi-stage routing is the most impactful sub-feature. Real encounters rarely need just one workflow step — an MRI encounter needs eligibility *and* prior auth *and* coding. Right now each encounter gets exactly one crew.

---

## Option 4: CI/CD, Test Coverage & Developer Experience

**Effort:** Small–Medium (3–5 days) | **Impact:** Medium (accelerates all future work)

There is no CI/CD at all, and several developer experience gaps.

### What it involves

- **GitHub Actions workflow:** lint (ruff/flake8), type-check (mypy/pyright), `pytest` on push/PR — with mock-only tests in CI (no LLM key required)
- **Type safety improvements:** Add `TypedDict` for the various `dict[str, Any]` return types from tools (currently the tool return shapes are undocumented contracts). Add `py.typed` marker
- **Test coverage reporting:** Wire `pytest-cov` (already a dev dependency) into CI with a coverage badge
- **Pre-commit hooks:** ruff format, ruff check, mypy
- **CHANGELOG.md:** Start tracking changes with Keep a Changelog format
- **Makefile / justfile:** Common commands (`make test`, `make lint`, `make serve`)

### Why this option

There are 20 test files but no automation. Every future iteration gets faster and safer with CI guardrails. The `TypedDict` work also prevents regressions in tool return shapes that currently rely on convention.

---

## Option 5: Batch Processing & Analytics Dashboard

**Effort:** Medium–Large (2–3 weeks) | **Impact:** High for demos

Move from single-encounter CLI processing to batch operations and add a visual dashboard for metrics.

### What it involves

- **Batch processing:** `rcm-agent process-batch <directory>` to process all encounters in a folder, with a summary report (success/failure/escalation counts, per-crew timings)
- **Enhanced analytics:** Extend `get_metrics()` and `get_denial_stats()` with time-series data, per-payer clean rates, average processing time per stage, denial trend detection
- **Dashboard:** A lightweight web UI (FastAPI + Jinja2, or Streamlit) showing:
  - Real-time encounter status board
  - Denial rate trends by payer and reason code
  - Escalation analysis (why encounters are being escalated)
  - Crew performance metrics
- **Export:** CSV/JSON export of metrics and denial analytics

### Why this option

The most compelling way to demonstrate value. A dashboard showing denial rates dropping or clean claim rates improving is far more persuasive than CLI output.

---

## Recommended Sequence

| Priority | Option | Rationale |
|----------|--------|-----------|
| 1st | **Option 4** — CI/CD + types (3–5 days) | Sets the foundation so everything after is safer |
| 2nd | **Option 1** — Claims Submission crew (1–2 weeks) | Completes the functional loop |
| 3rd | **Option 3** — Multi-stage routing (3–5 days) | Makes the pipeline realistic |
| 4th | **Option 2 or 5** | Choose Option 2 (hardening) if heading toward a pilot, or Option 5 (dashboard) if heading toward a stakeholder demo |
