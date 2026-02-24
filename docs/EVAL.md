# Evaluation Suite

The RCM Agent evaluation suite measures how well the app performs on synthetic encounters. It includes **router evaluation** (heuristic vs LLM classification) and **end-to-end (e2e) evaluation** (full pipeline with real LLM calls).

## Prerequisites

- **OpenRouter / LLM access:** Set `OPENAI_API_KEY`, `OPENAI_API_BASE`, and `OPENAI_MODEL_NAME` in `.env`. The project uses these for CrewAI/LiteLLM.
- **Router LLM comparison:** LLM routing is on by default; set `RCM_ROUTER_LLM_ENABLED=false` to use heuristic-only comparison.
- **E2E evals:** Always use the real LLM; ensure `OPENAI_API_KEY` is set.

## What the Suite Measures

### Router Evaluation

- **Heuristic vs LLM agreement:** Fraction of encounters where heuristic and LLM routing agree on primary stage and multi-stage sequence.
- **LLM failures:** Count of encounters where LLM classification failed or was unavailable.
- **Per-encounter records:** Disagreements and reasoning for tuning rules and prompts.

### E2E Evaluation

- **Pipeline success rate:** Fraction of encounters that complete without fatal error (NOT_ELIGIBLE, AUTH_DENIED, CLAIM_DENIED) and without inappropriate escalation.
- **Router alignment:** For encounters with golden expectations, fraction where pipeline-chosen stages match expected stages.
- **Prior auth coverage:** Fraction of encounters that needed prior auth where the pipeline produced an approval or denial.
- **Coding / claim readiness:** Fraction of encounters that reach claims submission or a clean outcome.

## How to Run

### Router-only

```bash
rcm-agent eval-router -o reports/router_eval.json
```

With custom examples directory:

```bash
rcm-agent eval-router --examples-dir data/examples -o reports/router_eval.json
```

LLM comparison is on by default; set `RCM_ROUTER_LLM_ENABLED=false` to disable.

### E2E-only

```bash
rcm-agent eval-e2e -o reports/e2e_eval.json
```

Requires `OPENAI_API_KEY` in `.env`.

Pipeline mode (`--pipeline`):

- `multi` (default): Multi-stage pipeline (`process_encounter_multi_stage`)
- `single`: Single-stage pipeline (`process_encounter`, one route → one crew)
- `both`: Runs both; writes `e2e_eval_single.json` and `e2e_eval_multi.json` to the output directory. With `eval-all`, that directory is `--output-dir` (default `reports`). With `eval-e2e`, it is the parent of `--output` when a file path is given (e.g. `-o reports/out.json` → `reports/`); if only a filename is given (e.g. `-o out.json`), reports are written to the current working directory.

### Full suite (router + e2e)

```bash
rcm-agent eval-all -o reports
```

Writes `reports/router_eval.json` and `reports/e2e_eval.json` (plus `e2e_eval.md` summary). Use `--golden <path>` to override the default golden file (repo `data/eval/golden.json`) for e2e comparison. Use `--pipeline single|multi|both` for e2e pipeline mode.

### Pytest

- **Default CI:** `pytest -m "not llm and not e2e"` — excludes LLM and e2e tests.
- **E2E tests:** `pytest -m e2e` — runs e2e tests (requires `OPENAI_API_KEY`).
- **LLM tests:** `pytest -m llm` — runs tests that call the LLM.
- **All tests:** `pytest` — runs everything (e2e/llm may skip if key missing).

## Reports

### Router report (`router_eval.json`)

- `total`, `agreements`, `disagreements`, `llm_failures`
- `agreement_rate`, `multi_stage_agreement_rate`
- `records`: per-encounter heuristic vs LLM comparison

### E2E report (`e2e_eval.json`)

- `total`, `pipeline_successes`, `pipeline_success_rate`, `pipeline_mode`
- `escalations`, `prior_auth_*`, `claim_readiness_rate`, `router_alignment_rate`
- `records`: per-encounter stages run, final status, success, artifacts

When `--pipeline both`, reports are written as `e2e_eval_single.json` and `e2e_eval_multi.json`.

### E2E markdown summary (`e2e_eval.md`)

Short human-readable summary with metrics and per-encounter table.

## Artifacts

Pipeline runs (e.g. process, e2e eval) can regenerate files under `data/artifacts/`. That directory is gitignored; avoid committing artifact-only churn in PRs.

## Golden Data

Optional expected outcomes for regression testing. Edit `data/eval/golden.json`:

```json
{
  "ENC-001": {
    "expected_stages": ["CODING_CHARGE_CAPTURE", "CLAIMS_SUBMISSION"],
    "expected_final_status": "CLAIM_ACCEPTED",
    "needs_prior_auth": false
  }
}
```

When golden data exists, e2e eval computes:

- **Router alignment rate:** fraction of encounters where pipeline stages include all `expected_stages`
- **Final status alignment rate:** when `expected_final_status` is set (non-null), fraction where actual final status matches
- **Needs prior auth alignment rate:** when `needs_prior_auth` is set, fraction where encounter’s prior-auth need matches the golden value

Golden keys: `expected_stages`, `expected_final_status`, `expected_escalation`, `expected_auth_outcome`, `needs_prior_auth`, `description`.

## Coverage and limitations

The eval suite covers the RCM agentic system within practical scope. Some behaviors remain out of scope.

**What is covered**

- **Router:** Heuristic vs LLM agreement (primary stage and multi-stage sequence) on all example encounters.
- **E2E pipeline:** Multi-stage (`process_encounter_multi_stage`) and single-stage (`process_encounter`) via `--pipeline single|multi|both`. Metrics: success rate, router alignment (vs golden), prior-auth coverage, claim readiness, escalation count.
- **Stages exercised:** Eligibility (005), prior auth (002, 008), coding + claims (001, 002), denial/appeal (004, 006, 007), escalation (003 via high charges).
- **Golden expectations:** All encounters (ENC-001 through ENC-008) have golden entries with `expected_stages`, `expected_final_status` (or null), `needs_prior_auth`, and optional `expected_escalation`.
- **Failure scenarios:** ENC-007 (CO-18 duplicate → CLAIM_DENIED), ENC-008 (prior auth denied → AUTH_DENIED). Eval sets `RCM_PRIOR_AUTH_MOCK_DENY_PAYER=AuthDenyPayer` by default so ENC-008 produces AUTH_DENIED.
- **Escalation:** ENC-003 has `expected_escalation: true`; success = pipeline correctly escalated.
- **Persistence/CLI:** `test_persistence_cli_pipeline` (pytest `-m e2e`) runs `rcm-agent process` and asserts stored state matches pipeline output via `EncounterRepository`.
- **Optional RAG:** Eval can run with `RCM_RAG_BACKEND=rag` (and Chroma index); report does not yet include RAG-quality metrics.
- **Optional HTTP backends:** Run `rcm-agent serve-mock` in one terminal, then `ELIGIBILITY_BACKEND=http PRIOR_AUTH_BACKEND=http rcm-agent eval-e2e` to exercise HTTP; documented as optional.

**What is not covered**

- **INTAKE / HUMAN_ESCALATION as router outputs:** Router can return INTAKE or HUMAN_ESCALATION; escalation is measured when pipeline returns HUMAN_ESCALATION due to `check_escalation()`, not router output.
- **RAG quality:** No retrieval precision/recall or guideline coverage metrics.
- **Production payer integrations:** No eval against real payer APIs.
- **Crew output quality:** No metrics on coding accuracy, appeal packet quality, or eligibility output correctness—only pipeline success and router alignment.

## Interpreting Metrics

- **Pipeline success rate:** High is good. For failure scenarios (ENC-007, ENC-008), success = pipeline correctly produced the expected failure status.
- **Router alignment:** High means pipeline stages match expectations; low may require routing rule or prompt tuning.
- **Prior auth coverage:** Should be 1.0 for encounters with auth-required CPT codes (e.g. 73721, 70450).
- **Claim readiness:** Fraction that reached claims submission; depends on prior stages completing successfully.
- **Escalation alignment:** When golden has `expected_escalation: true`, success = pipeline correctly escalated (e.g. ENC-003).

## Optional: RAG and HTTP backends

**RAG:** Set `RCM_RAG_BACKEND=rag` and ensure Chroma index is available. Eval will use RAG for coding/prior-auth; report records whether RAG was used but does not include retrieval quality metrics.

**HTTP backends:** To exercise the pipeline over HTTP:

1. Start mock server: `rcm-agent serve-mock` (default port 8000)
2. Run eval: `ELIGIBILITY_BACKEND=http PRIOR_AUTH_BACKEND=http CLAIMS_BACKEND=http rcm-agent eval-e2e -o reports/e2e_eval_http.json`

This is optional and not part of default CI.
