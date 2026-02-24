# Agent prompt: implement the rest of the RCM eval

Use this prompt to have an agent implement the missing pieces of the RCM Agent evaluation suite. The current eval is documented in [docs/EVAL.md](EVAL.md); the "Coverage and limitations" section lists what is **not** covered. Your job is to implement that remaining coverage.

## Context

- **Repo:** RCM Agent (`rcm_agent`). Hospital revenue-cycle agentic system: router (heuristic + LLM) → crews (eligibility, prior auth, coding, claims submission, denial/appeal) → tools (mock or HTTP backends, optional RAG).
- **Existing eval:** `rcm-agent eval-router` (heuristic vs LLM agreement) and `rcm-agent eval-e2e` (multi-stage pipeline only). E2E loads encounters from `data/examples/`, runs `process_encounter_multi_stage()` from `src/rcm_agent/crews/main_crew.py`, and compares to `data/eval/golden.json`. Reports go to `reports/`.
- **Key modules:** `src/rcm_agent/crews/e2e_eval.py`, `router_eval.py`, `main_crew.py` (`process_encounter` vs `process_encounter_multi_stage`), `src/rcm_agent/main.py` (CLI), `src/rcm_agent/db/repository.py` (persistence).

## Goal

Implement the rest of the eval so it is **comprehensive to the entire RCM agentic system** within practical scope (see tasks and out-of-scope below). Preserve existing behavior: current `eval-router` and `eval-e2e` commands and reports must keep working; extend them or add new subcommands/reports as needed.

## Tasks

Implement the following in a logical order. Prefer extending existing eval code and data over duplicating it.

### 1. Golden data for all encounters

- **File:** `data/eval/golden.json`
- **Action:** Add golden entries for ENC-003, ENC-005, ENC-006 (and any other encounters in `data/examples/` that lack one). Define `expected_stages`, `expected_final_status` (or null if N/A), `needs_prior_auth`, and optional `description` so that e2e eval can compute router alignment and final-status alignment for every encounter.
- **Reference:** ENC-003 triggers escalation (high charges); ENC-005 is eligibility → not eligible; ENC-006 is denial/appeal. Set expectations to match current pipeline behavior or desired behavior (document which).

### 2. Single-stage pipeline evaluation

- **Current gap:** E2E only runs `process_encounter_multi_stage()`. The system also supports `process_encounter()` (single-stage: route once → one crew).
- **Action:** Extend e2e eval (or add a mode) so that single-stage pipeline is evaluated on the same encounters (or a defined subset). Produce metrics comparable to multi-stage (e.g. success rate, stages run length 1, final status). Option: `--pipeline single | multi | both`; when `both`, write one report per mode or one combined report with clear per-mode metrics.
- **Files:** `src/rcm_agent/crews/e2e_eval.py`, optionally `src/rcm_agent/main.py` for CLI flags.

### 3. Failure-scenario encounters and golden expectations

- **Current gap:** No encounter has expected `AUTH_DENIED` or `CLAIM_DENIED`; no golden for remittance denial or prior-auth denial.
- **Action:** Add at least one synthetic encounter (or configure mock) that results in AUTH_DENIED, and one that results in CLAIM_DENIED (or remittance denied). Add corresponding golden entries with `expected_final_status` (e.g. `AUTH_DENIED`, `CLAIM_DENIED`) and optionally `expected_auth_outcome: "denied"`. Ensure e2e eval’s success/failure logic and golden comparison handle these (e.g. “success” for a scenario that is supposed to end in AUTH_DENIED means the pipeline correctly produced AUTH_DENIED).
- **Files:** `data/examples/` (new encounter JSONs or variants), `data/eval/golden.json`, and if needed `src/rcm_agent/crews/e2e_eval.py` (success criteria when golden expects a failure status).

### 4. Escalation and router-output coverage

- **Current gap:** Escalation is only measured when the pipeline returns HUMAN_ESCALATION due to `check_escalation()` (e.g. ENC-003). No explicit coverage for INTAKE or HUMAN_ESCALATION as router outputs.
- **Action:** Ensure at least one encounter has golden expectation that the pipeline ends in HUMAN_ESCALATION (e.g. ENC-003). Optionally add a metric or report field: “escalation alignment” (expected escalation vs actual). If the router can return INTAKE or HUMAN_ESCALATION, add one example or eval path that asserts that behavior (or document that it’s out of scope for this pass).

### 5. Persistence and CLI path (lightweight)

- **Current gap:** Eval calls the pipeline in process; it does not run `rcm-agent process` or verify DB/audit.
- **Action:** Add a small eval or test that (a) runs the pipeline via the CLI entrypoint that persists (e.g. `process` command) for one or two encounters, (b) reads back from the repository (e.g. status, stage, or audit rows) and asserts that stored state matches what the pipeline produced. Use an in-memory or temp DB so it’s deterministic and fast. This can be a pytest integration test marked `e2e` or a separate “eval-persistence” script; document in EVAL.md.

### 6. Optional: RAG and integration backends

- **Scope:** Only if feasible without heavy new infrastructure.
- **RAG:** Add an optional e2e run with `RCM_RAG_BACKEND=rag` (and Chroma index available) and record in the report whether RAG was used; no need for full “RAG quality” metrics in this pass.
- **HTTP backends:** Add an optional eval mode that uses `ELIGIBILITY_BACKEND=http`, `PRIOR_AUTH_BACKEND=http` with `rcm-agent serve-mock` (or equivalent) so that the pipeline is exercised over HTTP at least for one encounter; document how to run it and that it’s optional.

### 7. Documentation and report shape

- **Action:** Update [docs/EVAL.md](EVAL.md): (1) Extend “Coverage and limitations” to reflect the new coverage (single-stage, failure scenarios, golden for all encounters, persistence/CLI, optional RAG/HTTP). (2) Document any new CLI flags, report files, or golden keys. (3) Keep “Interpreting Metrics” in sync with new metrics.
- **Reports:** If you add new reports (e.g. single-stage e2e, persistence), add their paths and meanings to EVAL.md.

## Out of scope (do not implement in this pass)

- **Crew-level output quality:** No metrics for coding accuracy, appeal packet quality, or eligibility output correctness (beyond pipeline success and router alignment).
- **Full RAG quality evaluation:** No retrieval precision/recall or guideline coverage metrics.
- **Production payer integrations:** No eval against real payer APIs.

## Acceptance criteria

- All existing eval commands and tests still pass: `rcm-agent eval-router`, `rcm-agent eval-e2e`, `rcm-agent eval-all`, and pytest for eval-related tests (e.g. `tests/test_intelligent_routing.py`, `tests/test_e2e_eval.py`, `tests/test_cli.py`).
- Golden data exists for every encounter in `data/examples/` used by e2e eval.
- At least one encounter has expected AUTH_DENIED and one has expected CLAIM_DENIED (or remittance denied), with golden and success logic updated.
- Single-stage pipeline is evaluated (separate report or mode) with documented metrics.
- Persistence/CLI path is exercised and asserted in at least one automated test or eval script.
- EVAL.md is updated to describe new coverage and how to run it.

## How to run existing eval (for reference)

```bash
source .venv/bin/activate
rcm-agent eval-all -o reports
# Reports: reports/router_eval.json, reports/e2e_eval.json, reports/e2e_eval.md
```

Use `OPENAI_API_KEY` in `.env` for LLM-backed router and crews. Optional: `RCM_ROUTER_LLM_ENABLED=false` for heuristic-only router eval.
