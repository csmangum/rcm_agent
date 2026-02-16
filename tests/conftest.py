"""Pytest configuration and shared fixtures."""

import json
from pathlib import Path

import pytest

from rcm_agent.models import Encounter


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


def _load_encounter(examples_dir: Path, filename: str) -> Encounter:
    with open(examples_dir / filename, encoding="utf-8") as f:
        return Encounter.model_validate(json.load(f))


@pytest.fixture
def encounter_001(examples_dir: Path) -> Encounter:
    """ENC-001: routine office visit (Aetna, eligible)."""
    return _load_encounter(examples_dir, "encounter_001_routine_visit.json")


@pytest.fixture
def encounter_002(examples_dir: Path) -> Encounter:
    """ENC-002: MRI knee with prior auth (UnitedHealthcare)."""
    return _load_encounter(examples_dir, "encounter_002_mri_with_auth.json")


@pytest.fixture
def encounter_005(examples_dir: Path) -> Encounter:
    """ENC-005: eligibility mismatch (Anthem, lapsed)."""
    return _load_encounter(examples_dir, "encounter_005_eligibility_mismatch.json")
