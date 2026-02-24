---
name: run-lint
description: Run Ruff lint and format checks for rcm_agent. Use when the user asks to run the linter, lint tests, or check code style.
---

# Run Lint Tests

## How to run

1. **Use the project venv** – Ruff is a dev dependency; run from `.venv` so it is on PATH:
   ```bash
   . .venv/bin/activate
   ```

2. **Lint (Ruff check)**:
   ```bash
   ruff check src/ tests/
   ```

3. **Format check**:
   ```bash
   ruff format --check src/ tests/
   ```

One-liner from repo root:
```bash
. .venv/bin/activate && ruff check src/ tests/ && ruff format --check src/ tests/
```

## Auto-fix

To fix issues Ruff can fix automatically (e.g. unused imports, f-strings):
```bash
ruff check src/ tests/ --fix
```
Then re-run the full check to confirm.

## What CI runs

The GitHub Actions `lint` job runs the same commands (after `pip install -e ".[dev]"`): `ruff format --check src/ tests/` then `ruff check src/ tests/`.
