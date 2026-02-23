# rcm_agent

Hospital Revenue Cycle Management (RCM) Agent – a POC extending the [auto-agent](https://github.com/csmangum/auto-agent) architecture for provider-side workflows: eligibility verification, prior authorization, coding/charge capture, and denial/appeal handling.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate   # or: .venv\Scripts\activate on Windows
pip install -e ".[dev]"
```

Copy environment template and set your keys:

```bash
cp .env.example .env
# Edit .env with OPENAI_API_KEY, etc.
```

## Configuration

### RAG (coding guidelines and payer policies)

- **Default:** `RCM_RAG_BACKEND=mock` uses canned snippets; no Chroma index required.
- **Real RAG:** Set `RCM_RAG_BACKEND=rag` and ensure a populated Chroma index (e.g. run `medicare_rag` ingest). Set `RCM_RAG_CHROMA_DIR` to the Chroma directory; `~` is expanded and the default is `~/medicare_rag/data/chroma`.

## Usage

```bash
rcm-agent --help
rcm-agent process data/examples/encounter_001_routine_visit.json
rcm-agent process data/examples/encounter_004_denial_scenario.json   # denial/appeal crew
rcm-agent status ENC-001
rcm-agent history ENC-001
rcm-agent metrics
rcm-agent denial-stats   # denial analytics (reason codes, type, payer)
```

## Tests

```bash
pytest
```

## Project structure

- `src/rcm_agent/` – main package (agents, crews, tools, models, db, config, rag, observability)
- `data/examples/` – synthetic encounter JSONs
- `data/rag_corpus/` – payer policies and coding guidelines (Phase 4)
- `tests/` – pytest tests
