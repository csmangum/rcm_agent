# Hospital RCM Agent -- Phased Implementation Plan

The upstream [auto-agent](https://github.com/csmangum/auto-agent) provides the foundational architecture: CrewAI orchestration, router-based crew delegation, SQLite persistence with audit trails, RAG infrastructure, human-in-the-loop escalation, CLI interface, and LLM observability. This plan adapts that architecture for provider-side RCM workflows.

---

## Phase 0: Scaffolding and Environment Setup (Days 1-2)

**Goal:** Establish the project skeleton, dependencies, and dev environment so all subsequent phases build on a working foundation.

- Copy the `auto-agent` project structure into `rcm_agent/`, renaming the package from `claim_agent` to `rcm_agent`
- Set up `pyproject.toml` with dependencies: `crewai`, `litellm`, `langsmith`, `pydantic`, `sentence-transformers`, `click` (CLI), `sqlite3` (stdlib)
- Create `.env.example` with RCM-specific env vars (LLM keys, DB path, escalation thresholds, RAG paths)
- Create virtualenv and verify `pip install -e .` works
- Set up directory structure:

```
src/rcm_agent/
├── main.py
├── agents/
├── crews/
├── tools/
├── models/
├── db/
├── config/
├── rag/
├── observability/
└── utils/
data/
├── examples/          # synthetic encounter JSONs
├── rag_corpus/        # payer policies, coding guidelines
└── rcm.db
tests/
```

- Establish basic `pytest` test infrastructure with a venv
- Create `data/examples/` with 3-5 synthetic encounter JSONs (routine visit, MRI w/ auth, inpatient surgery, denial scenario, eligibility mismatch)

**Exit Criteria:** `pip install -e .` succeeds, `rcm-agent --help` prints usage, synthetic data files exist, `pytest` runs (even if no tests yet).

---

## Phase 1: Domain Models, Database, and CLI Shell (Days 3-5)

**Goal:** Replace the insurance claim domain with hospital encounter domain throughout models, DB, and CLI.

### 1a. Domain Models

Adapt `auto-agent/src/claim_agent/models/claim.py` into new Pydantic models:

- **Encounter** (replaces `ClaimInput`): `encounter_id`, `patient` (age, gender, zip), `insurance` (payer, member_id, plan_type), `date`, `type` (outpatient_procedure, inpatient, office_visit, emergency), `procedures` (list of code+description), `diagnoses` (list of code+description), `clinical_notes`, `documents`
- **RcmStage** enum (replaces `ClaimType`): `ELIGIBILITY_VERIFICATION`, `PRIOR_AUTHORIZATION`, `CODING_CHARGE_CAPTURE`, `CLAIMS_SUBMISSION`, `DENIAL_APPEAL`, `HUMAN_ESCALATION`
- **EncounterOutput** (replaces `ClaimOutput`): `encounter_id`, `stage`, `status`, `actions_taken`, `artifacts` (generated docs), `message`, `raw_result`
- **PriorAuthRequest**: `auth_id`, `encounter_id`, `payer`, `procedure_codes`, `clinical_justification`, `status`, `submitted_at`, `decision`, `decision_date`
- **ClaimSubmission**: `claim_id`, `encounter_id`, `payer`, `total_charges`, `icd_codes`, `cpt_codes`, `modifiers`, `status`, `submitted_at`
- **EscalationOutput**: Reuse pattern from auto-agent, adapted with RCM-specific reasons (high-dollar, oncology, incomplete clinical docs, low coding confidence)

### 1b. SQLite Schema

Extend `auto-agent/src/claim_agent/db/` pattern:

- **encounters** table: mirrors Encounter model fields + `stage`, `status`, `created_at`, `updated_at`
- **encounter_audit_log** table: `encounter_id`, `action`, `old_status`, `new_status`, `details`, `created_at`
- **workflow_runs** table: `encounter_id`, `stage`, `router_output`, `workflow_output`, `created_at`
- **prior_auth_requests** table: tracks auth lifecycle
- **claim_submissions** table: tracks claim lifecycle
- Status constants: `PENDING`, `PROCESSING`, `ELIGIBLE`, `NOT_ELIGIBLE`, `AUTH_REQUIRED`, `AUTH_APPROVED`, `AUTH_DENIED`, `CODED`, `CLAIM_SUBMITTED`, `CLAIM_ACCEPTED`, `CLAIM_DENIED`, `NEEDS_REVIEW`, `ESCALATED`

### 1c. CLI Shell

Adapt `auto-agent/src/claim_agent/main.py`:

- `rcm-agent process <encounter.json>` -- process an encounter through the pipeline
- `rcm-agent status <encounter_id>` -- get current status
- `rcm-agent history <encounter_id>` -- get audit trail
- `rcm-agent metrics` -- show aggregate metrics (clean rate, escalation %, turnaround)
- Wire CLI to DB repository; crew orchestration is stubbed (returns mock results)

**Exit Criteria:** Models validate synthetic JSON, DB schema initializes, CLI commands work with stubbed crew logic, unit tests pass for models and DB layer.

---

## Phase 2: Router Crew and Escalation Logic (Days 6-9)

**Goal:** Build the router that classifies encounters and routes them to the correct specialized crew, plus deterministic escalation checks.

### 2a. Router Agent

Adapt `auto-agent`'s router pattern in `crews/main_crew.py`:

- Router agent receives Encounter JSON
- Classifies into `RcmStage` based on:
  - Missing/expired insurance info --> `ELIGIBILITY_VERIFICATION`
  - Procedure requires prior auth (configurable CPT list) --> `PRIOR_AUTHORIZATION`
  - Missing/incomplete coding --> `CODING_CHARGE_CAPTURE`
  - Ready for submission --> `CLAIMS_SUBMISSION` (Phase 4 stretch)
  - Denied claim needing appeal --> `DENIAL_APPEAL` (Phase 4 stretch)
- Pre-routing heuristics (before LLM call):
  - Check if insurance info is present and non-expired
  - Check procedure codes against known auth-required list
  - Check if ICD/CPT codes are present and complete
- Router prompt in `config/agents.yaml` and `config/tasks.yaml`

### 2b. Escalation Logic

Adapt `auto-agent`'s deterministic escalation from `tools/logic.py`:

- Configurable triggers via `.env`:
  - `ESCALATION_CONFIDENCE_THRESHOLD` (default: 0.85)
  - `ESCALATION_HIGH_VALUE_THRESHOLD` (default: $5,000)
  - `ESCALATION_ONCOLOGY_FLAG` (always escalate oncology encounters)
  - `ESCALATION_INCOMPLETE_DATA_FLAG` (missing clinical notes or documents)
- Escalation check runs after router, before crew dispatch
- If escalated: set status `NEEDS_REVIEW`, save reasons, stop pipeline
- Escalation reasons: low confidence, high dollar value, oncology/complex case, incomplete documentation

### 2c. Config Layer

Adapt `config/settings.py` for RCM-specific settings:

- `get_escalation_config()` with RCM thresholds
- `get_auth_required_procedures()` -- list of CPT codes requiring prior auth
- `get_payer_config()` -- payer-specific rules

**Exit Criteria:** Router correctly classifies at least 3 encounter types from synthetic data, escalation triggers on configurable conditions, full audit trail in SQLite, unit tests for router classification and escalation logic.

---

## Phase 3: Specialized Crews (Days 10-18)

**Goal:** Implement the 3 core crews that do the actual RCM work. Build them sequentially, each taking ~3 days.

### 3a. Eligibility Verification Crew (Days 10-12)

**Agents:** eligibility_checker, benefits_analyzer, gap_flagger

**Tools:**

- `check_member_eligibility(payer, member_id, date)` -- mock payer API call returning eligibility status, plan details, effective dates
- `verify_benefits(payer, member_id, procedure_codes)` -- mock benefits check (covered/not covered, copay, coinsurance, deductible remaining)
- `check_coordination_of_benefits(patient)` -- detect secondary insurance
- `flag_coverage_gaps(eligibility_result)` -- identify inactive policies, terminated coverage, out-of-network issues

**Flow:**

```
Encounter --> check_member_eligibility --> verify_benefits --> flag_coverage_gaps --> Output
```

**Output:** Eligibility status, coverage details, any gaps/flags, recommendation (proceed / hold / escalate)

**Mock API:** Simple Python dict-based mock returning canned responses keyed by `(payer, member_id)`. Optionally a FastAPI endpoint for more realistic testing.

### 3b. Prior Authorization Crew (Days 13-15)

**Agents:** clinical_extractor, policy_matcher, auth_assembler, status_tracker

**Tools:**

- `extract_clinical_indicators(clinical_notes)` -- LLM-based extraction of diagnoses, symptoms, failed treatments, medical necessity indicators
- `search_payer_policies(payer, procedure_code)` -- RAG search over payer medical policies (ties into Phase 4 RAG)
- `assemble_auth_packet(encounter, clinical_indicators, policy_matches)` -- generate mock prior auth request document
- `submit_auth_request(auth_packet)` -- mock submission returning auth_id + pending status
- `poll_auth_status(auth_id)` -- mock status check returning approved/denied/pending

**Flow:**

```
Encounter --> extract_clinical_indicators --> search_payer_policies (RAG)
         --> assemble_auth_packet --> submit_auth_request --> poll_auth_status --> Output
```

**Output:** Auth request artifact (mock PDF/JSON), auth status, approval/denial reason, next steps

### 3c. Coding and Charge Capture Crew (Days 16-18)

**Agents:** code_suggester, charge_reviewer, compliance_checker

**Tools:**

- `suggest_codes(clinical_notes, encounter_type)` -- LLM + RAG to suggest ICD-10-CM, CPT, HCPCS codes from clinical narrative
- `validate_code_combinations(icd_codes, cpt_codes)` -- check against NCCI edits, validate modifier usage
- `identify_missing_charges(encounter, suggested_codes)` -- flag procedures documented but not coded, missing modifiers
- `search_coding_guidelines(query)` -- RAG over ICD-10/CPT/HCPCS guidelines
- `calculate_expected_reimbursement(codes, payer)` -- rough estimate based on fee schedule

**Flow:**

```
Encounter --> suggest_codes (LLM+RAG) --> validate_code_combinations
         --> identify_missing_charges --> compliance_check --> Output
```

**Output:** Suggested code set, validation results, missing charge flags, expected reimbursement estimate, confidence score

**Exit Criteria:** Each crew processes its relevant synthetic encounters end-to-end, artifacts are generated and saved, audit trail captures full reasoning chain, unit tests for each crew's tools and logic.

---

## Phase 4: RAG Infrastructure and Knowledge Base (Parallel with Phase 3, Days 10-18)

**Goal:** Stand up the RAG pipeline with healthcare-specific knowledge so the Prior Auth and Coding crews have real retrieval backing.

### 4a. RAG Corpus Preparation

Create/curate documents in `data/rag_corpus/`:

- **Payer Medical Policies** (2-3 synthetic PDFs/text files): UnitedHealthcare MRI policy, Aetna prior auth requirements, generic commercial plan policy
- **ICD-10-CM Guidelines** (subset): relevant sections for the synthetic encounter types (musculoskeletal, pain codes)
- **CPT/HCPCS Guidelines** (subset): imaging codes, E&M codes, surgical codes relevant to synthetic data
- **NCCI Edits** (subset): common code pair edits relevant to encounters
- **CMS Prior Auth Requirements**: summary of 2026 CMS interoperability rules

### 4b. RAG Pipeline

Reuse `auto-agent`'s RAG infrastructure (`rag/` directory):

- Adapt chunker for healthcare documents (policy sections, coding chapters)
- Adapt vector store with healthcare-specific metadata filtering: `payer`, `document_type` (policy, guideline, regulation), `code_system` (ICD-10, CPT, HCPCS)
- Reuse sentence-transformers embeddings
- Create RCM-specific RAG tools:
  - `search_payer_policies(payer, procedure_code, query)` -- semantic search over payer policies
  - `search_coding_guidelines(code_system, query)` -- search ICD-10/CPT guidelines
  - `search_ncci_edits(cpt_code_1, cpt_code_2)` -- check NCCI edit pairs
  - `search_cms_requirements(topic)` -- search CMS regulations

**Exit Criteria:** RAG returns relevant snippets for each synthetic encounter scenario, retrieval quality is reasonable (manual spot-check), vector store caches properly.

---

## Phase 5: Integration, Metrics, and Polish (Days 19-22)

**Goal:** Wire everything together end-to-end, add observability, compute metrics, and ensure the demo is solid.

### 5a. End-to-End Pipeline Integration

- Wire router --> escalation check --> specialized crew dispatch in `main_crew.py`
- Ensure all 3-5 synthetic encounters process through full pipeline without fatal errors
- Verify artifacts are generated and saved (auth request JSON, coded encounter, eligibility report)
- Verify SQLite captures complete state transitions and audit trail

### 5b. Observability

- Reuse LiteLLM + LangSmith integration from auto-agent
- Ensure traces show clean agent reasoning and tool calls for each encounter
- Add structured logging for key decision points (router classification, escalation decision, crew output)

### 5c. Metrics

Implement `rcm-agent metrics` command:

- **First-pass clean rate**: % of encounters that process without escalation or errors
- **Escalation rate**: % of encounters requiring human review
- **Simulated turnaround time**: average processing duration
- **Per-crew success rate**: success/failure by crew type
- **Auth approval rate**: % of prior auth requests approved (mock)

### 5d. Documentation and Polish

- Update `README.md` with project description, setup instructions, usage examples
- Ensure `.env.example` is complete and documented
- Clean up any rough edges, improve error messages
- Final pass on synthetic data quality

**Exit Criteria (MVP Acceptance):**

- [ ] CLI commands work: `rcm-agent process`, `rcm-agent status`, `rcm-agent history`, `rcm-agent metrics`
- [ ] Router correctly classifies and routes at least 3 encounter types
- [ ] 3 specialized crews execute end-to-end on synthetic data
- [ ] RAG returns relevant snippets from payer policies and coding guidelines
- [ ] Human escalation triggers on configurable conditions
- [ ] SQLite schema captures full reasoning chain
- [ ] At least 4 synthetic encounters process successfully with outputs saved
- [ ] LangSmith traces show clean agent reasoning
- [ ] Basic metrics command shows success/failure/escalation counts

---

## Phase 6 (Stretch / Post-MVP): Denial and Appeal Crew

**Goal:** Add the Denial & Appeal crew as Phase 2 scope from the PLAN.md.

- **Denial Crew**: Analyze denial reason codes (CO-4, CO-197, PR-96, etc.), classify denial type (clinical, administrative, technical), determine appeal viability
- **Appeal Crew**: Generate appeal letter drafts using RAG over payer policies + clinical documentation, assemble appeal packet
- Denial pattern analytics (most common denial codes, payer-specific trends)
- Mock FHIR/EDI endpoints for more realistic integration testing

---

## Timeline Summary

| Phase | Description | Days | Calendar |
|-------|-------------|------|----------|
| **Phase 0** | Scaffolding & Setup | Days 1-2 | Feb 16-17 |
| **Phase 1** | Domain Models, DB, CLI | Days 3-5 | Feb 18-20 |
| **Phase 2** | Router Crew & Escalation | Days 6-9 | Feb 21-24 |
| **Phase 3** | Specialized Crews (3) | Days 10-18 | Feb 25 - Mar 5 |
| **Phase 4** | RAG Infrastructure | Days 10-18 | Feb 25 - Mar 5 (parallel w/ Phase 3) |
| **Phase 5** | Integration & Polish | Days 19-22 | Mar 6-9 |
| **Phase 6** | Denial & Appeal (stretch) | Post-MVP | TBD |
