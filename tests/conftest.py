"""Pytest configuration and shared fixtures."""

import json
from pathlib import Path

import pytest


@pytest.fixture
def examples_dir() -> Path:
    """Path to data/examples directory."""
    return Path(__file__).resolve().parent.parent / "data" / "examples"


@pytest.fixture
def sample_encounter_json(examples_dir: Path) -> dict:
    """Load first synthetic encounter as sample data."""
    path = examples_dir / "encounter_001_routine_visit.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)
