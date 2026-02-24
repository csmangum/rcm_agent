.PHONY: install dev lint format typecheck test test-cov serve clean

install:
	pip install -e .

dev:
	pip install -e ".[dev]"
	pre-commit install

lint:
	ruff check src/ tests/

format:
	ruff format src/ tests/

typecheck:
	mypy src/rcm_agent/

test:
	pytest tests/ -m "not llm and not e2e"

test-cov:
	pytest tests/ -m "not llm and not e2e" --cov=rcm_agent --cov-report=term-missing

serve:
	uvicorn rcm_agent.integrations.mock_server:app --port 8000

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	rm -f coverage.xml .coverage
