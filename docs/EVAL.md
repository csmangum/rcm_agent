# Evaluation Suite

The RCM Agent evaluation suite measures how well the app performs on synthetic encounters. It includes **router evaluation** (heuristic vs LLM classification) and **end-to-end (e2e) evaluation** (full pipeline with real LLM calls).

## Prerequisites

- **OpenRouter / LLM access:** Set `OPENAI_API_KEY`, `OPENAI_API_BASE`, and `OPENAI_MODEL_NAME` in `.env`. The project uses these for CrewAI/LiteLLM.
- **Router LLM comparison:** Set `RCM_ROUTER_LLM_ENABLED=true` in `.env` to compare heuristic vs LLM routing (otherwise router eval uses heuristic only).
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

For LLM comparison, set `RCM_ROUTER_LLM_ENABLED=true` in `.env` before running.

### E2E-only

```bash
rcm-agent eval-e2e -o reports/e2e_eval.json
```

Requires `OPENAI_API_KEY` in `.env`.

### Full suite (router + e2e)

```bash
rcm-agent eval-all -o reports
```

Writes `reports/router_eval.json` and `reports/e2e_eval.json` (plus `e2e_eval.md` summary). Use `--golden <path>` to override the default golden file (repo `data/eval/golden.json`) for e2e comparison.

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

- `total`, `pipeline_successes`, `pipeline_success_rate`
- `escalations`, `prior_auth_*`, `claim_readiness_rate`, `router_alignment_rate`
- `records`: per-encounter stages run, final status, success, artifacts

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
    "expected_final_status": "CLAIM_SUBMITTED",
    "needs_prior_auth": false
  }
}
```

When golden data exists, e2e eval computes:

- **Router alignment rate:** fraction of encounters where pipeline stages include all `expected_stages`
- **Final status alignment rate:** when `expected_final_status` is set (non-null), fraction where actual final status matches
- **Needs prior auth alignment rate:** when `needs_prior_auth` is set, fraction where encounter’s prior-auth need matches the golden value

## Interpreting Metrics

- **Pipeline success rate:** High is good. Low may indicate escalation thresholds, mock backend behavior, or LLM variability.
- **Router alignment:** High means pipeline stages match expectations; low may require routing rule or prompt tuning.
- **Prior auth coverage:** Should be 1.0 for encounters with auth-required CPT codes (e.g. 73721, 70450).
- **Claim readiness:** Fraction that reached claims submission; depends on prior stages completing successfully.
