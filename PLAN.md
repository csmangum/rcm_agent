**Title:** [POC] Implement Hospital Revenue Cycle Management (RCM) Agent – Fork & Extend auto-agent for Provider-Side Workflows

**Labels:** enhancement, poc, healthcare, high-priority  
**Assignees:** @peril10  
**Milestone:** Hospital RCM POC (create if needed)

### User Story
As a hospital revenue cycle leader / developer building agentic proofs-of-concept,  
I want an autonomous agent system that mirrors the insurance-side [`auto-agent`](https://github.com/csmangum/auto-agent) architecture but handles **provider-side** revenue cycle tasks (eligibility verification → prior authorization → coding/charge capture → clean claim generation → denial/appeal handling),  
so that we can demonstrate high-ROI automation to hospitals, reduce administrative burden, speed up cash collection, and lower denial rates — all while reusing ~70% of the existing codebase.

### Background & Business Value
Hospitals lose billions annually to inefficient RCM:
- Claim denial rates ~11–19% (many avoidable)
- Prior authorization is one of the top denial drivers (20–32% of issues)
- Eligibility mismatches & missing auths cause massive rework
- Cost to collect remains high; agentic AI has potential to cut it 30–60% (McKinsey 2026 estimates)
- 2026 brings tighter CMS prior auth rules + API mandates → automation window is now

This POC directly extends the proven `auto-agent` pattern (router + specialized crews + persistent SQLite state + human-in-the-loop + RAG + observability) from payer/claims to provider/encounter workflows.

### Proposed Scope (MVP – 3–4 weeks target)
1. **Core re-use (almost no changes needed)**
   - CrewAI pattern & task delegation
   - Router crew logic
   - SQLite persistence + audit trail
   - Human-in-the-loop escalation (configurable thresholds)
   - LiteLLM + LangSmith observability
   - CLI interface (`agent process ...`, `agent status ...`, etc.)
   - RAG infrastructure (just swap knowledge base)

2. **New domain models & state**
   - Replace `Claim` with `Encounter` / `PatientCase`
   - Add lightweight models: `PriorAuthRequest`, `ClaimSubmission`, `Denial`, `Appeal`

3. **Router Crew**
   - Input: de-identified Encounter JSON
   - Classifies → routes to:
     - Eligibility & Benefits Verification Crew
     - Prior Authorization Crew
     - Coding & Charge Capture Crew
     - Claims Submission & Follow-up Crew
     - Denial & Appeal Crew (stretch goal / phase 2)
     - Human Escalation (high $$, low confidence, incomplete data, oncology/high-value, etc.)

4. **Specialized Crews (start with 3)**
   - **Eligibility Verification Crew**
     - Mock / real-time eligibility check logic
     - Flag coverage gaps, inactive policies, coordination of benefits
   - **Prior Authorization Crew**
     - Extract clinical indicators from notes/docs
     - RAG against payer medical policies + guidelines
     - Assemble & "submit" mock auth packet
     - Poll mock status → notify on approval/denial
   - **Coding & Charge Capture Crew**
     - Suggest ICD-10-CM, CPT, HCPCS from clinical narrative
     - RAG over 2025/2026 coding guidelines + NCCI edits
     - Identify missing charges / modifiers

5. **Data & RAG**
   - Synthetic encounter JSONs (3–5 examples: routine visit, MRI w/ auth, inpatient surgery, denial scenario)
   - RAG corpus: sample payer policies (PDF/text), ICD-10/CPT guidelines, CMS docs

6. **Outputs & Visibility**
   - Updated encounter status + generated artifacts (auth request PDF mock, clean claim JSON, appeal letter draft)
   - Full trace in SQLite + LangSmith
   - Simple metrics: first-pass "clean rate", escalation %, simulated turnaround time

### Non-Goals (out of MVP scope)
- Real EHR/EDI/FHIR integrations
- Production HIPAA pipeline (use synthetic data only; note prod path: Azure OpenAI/Bedrock + BAA)
- Full denial management & appeals (add in phase 2)
- Patient-facing comms (billing questions, payment plans)

### Technical Approach / Diff from auto-agent
- Rename `claim` → `encounter` throughout (models, tables, files)
- Update router prompt & task enum: `EncounterType` or `RcmStage`
- Reuse tools pattern → add new tools:
  - Mock payer eligibility API (FastAPI helper endpoint?)
  - Mock prior auth submit/poll
  - Code suggester (LLM + RAG)
- Keep same `.env` + config style for escalation rules
- Reuse evaluation harness → adapt to measure "clean claim" score, auth approval rate, etc.

### Acceptance Criteria
- [ ] Repo forked / new repo created with clear README update ("Hospital RCM POC – extension of auto-agent")
- [ ] CLI commands work: `rcm-agent process encounter_001.json`, `rcm-agent status ENC-001`, `rcm-agent history`
- [ ] Router correctly classifies & routes at least 3 encounter types
- [ ] 3 specialized crews execute end-to-end on synthetic data without fatal errors
- [ ] RAG returns relevant snippets from payer policies / coding guidelines
- [ ] Human escalation triggers on configurable conditions (e.g. confidence < 0.85, amount > $5000)
- [ ] SQLite schema extended + audit trail captures full reasoning chain
- [ ] At least 4 synthetic encounters process successfully with outputs saved
- [ ] LangSmith traces show clean agent reasoning & tool calls
- [ ] Basic metrics command shows success/failure/escalation counts

### Sample Synthetic Input (add to /data/examples)
```json
{
  "encounter_id": "ENC-001",
  "patient": {"age": 58, "gender": "M", "zip": "850xx"},
  "insurance": {"payer": "UnitedHealthcare", "member_id": "XXX", "plan_type": "PPO"},
  "date": "2026-02-10",
  "type": "outpatient_procedure",
  "procedures": [{"code": "73721", "description": "MRI knee"}],
  "diagnoses": [{"code": "M25.561", "description": "Pain in right knee"}],
  "clinical_notes": "Patient with chronic right knee pain, failed conservative therapy including PT and NSAIDs. MRI ordered to evaluate for meniscal tear.",
  "documents": ["clinic_note.txt", "physician_order.pdf"]
}
```

### Risks / Mitigations
- LLM hallucination on coding → mitigation: strong RAG + confidence scoring + human review path
- Scope creep → stick to 3 crews + synthetic data
- Payer policy freshness → use dated samples; note prod needs dynamic refresh

### Phase 2 Ideas (after MVP demo)
- Denial crew + appeal letter generation
- Mock FHIR/EDI endpoints
- Denial pattern analytics dashboard
- Multi-payer policy RAG
- Integration with real mock EHR (e.g. OpenEMR or synthetic FHIR server)