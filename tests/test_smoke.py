"""Smoke tests: import and basic validation."""

import json
from pathlib import Path


def test_import_rcm_agent() -> None:
    """Package can be imported."""
    import rcm_agent  # noqa: F401

    assert rcm_agent.__version__ == "0.1.0"


def test_synthetic_encounter_json_loads(examples_dir: Path) -> None:
    """Synthetic encounter JSON files exist and are valid."""
    examples = list(examples_dir.glob("encounter_*.json"))
    assert len(examples) >= 3, "Expected at least 3 synthetic encounter files"

    for path in examples:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        assert "encounter_id" in data
        assert "patient" in data
        assert "insurance" in data
        assert "date" in data
        assert "type" in data
        assert "procedures" in data
        assert "diagnoses" in data
        assert "clinical_notes" in data
        assert "documents" in data


def test_sample_encounter_has_expected_keys(sample_encounter_json: dict) -> None:
    """Sample encounter fixture has required schema keys."""
    required = {"encounter_id", "patient", "insurance", "date", "type", "procedures", "diagnoses", "clinical_notes", "documents"}
    assert set(sample_encounter_json.keys()) >= required
