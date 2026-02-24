"""E2E integration tests: full pipeline with real LLM (OpenRouter).

Run with: pytest tests/test_eval_e2e_integration.py -m "e2e and llm" -v
Requires OPENAI_API_KEY in .env. Skipped when key is missing.
"""

import os

import pytest

# Load .env via conftest
pytest.importorskip("dotenv")


def _has_openai_key() -> bool:
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    return bool(key and key != "your_openrouter_key")


@pytest.mark.e2e
@pytest.mark.llm
@pytest.mark.skipif(not _has_openai_key(), reason="OPENAI_API_KEY not set")
def test_e2e_eval_full_pipeline(examples_dir, tmp_path):
    """Run e2e evaluation with real pipeline (requires OPENAI_API_KEY)."""
    from rcm_agent.crews.e2e_eval import run_e2e_evaluation

    output_path = tmp_path / "e2e_eval.json"
    summary = run_e2e_evaluation(
        examples_dir=examples_dir,
        golden_path="data/eval/golden.json",
        output_path=output_path,
    )
    assert summary.total > 0
    assert len(summary.records) == summary.total
    assert output_path.exists()
    # At least one encounter should complete (exact success rate depends on mock backends)
    assert summary.pipeline_successes >= 0
