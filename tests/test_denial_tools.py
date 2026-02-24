"""Unit tests for denial and appeal tools."""

import json
from pathlib import Path

from rcm_agent.models import Encounter
from rcm_agent.tools.appeal import (
    assemble_appeal_packet,
    generate_appeal_letter,
    search_payer_policies_for_appeal,
)
from rcm_agent.tools.denial import (
    DENIAL_REASON_CODE_CATALOG,
    DenialType,
    assess_appeal_viability,
    classify_denial_type,
    parse_denial_reason_codes,
)


def _load_encounter(examples_dir: Path, filename: str) -> Encounter:
    with open(examples_dir / filename, encoding="utf-8") as f:
        return Encounter.model_validate(json.load(f))


def test_parse_denial_reason_codes_from_denial_info(examples_dir: Path) -> None:
    """parse_denial_reason_codes uses encounter.denial_info.reason_codes when present."""
    encounter = _load_encounter(examples_dir, "encounter_004_denial_scenario.json")
    assert encounter.denial_info is not None
    codes = parse_denial_reason_codes(encounter)
    assert codes == ["CO-4", "PR-96"]


def test_parse_denial_reason_codes_from_notes(examples_dir: Path) -> None:
    """parse_denial_reason_codes parses CO-4, PR-96 from clinical_notes when no denial_info."""
    encounter = _load_encounter(examples_dir, "encounter_004_denial_scenario.json")
    # Remove denial_info to force notes parsing
    encounter = encounter.model_copy(update={"denial_info": None})
    codes = parse_denial_reason_codes(encounter)
    assert "CO-4" in codes
    assert "PR-96" in codes


def test_classify_denial_type_administrative() -> None:
    """PR-96, CO-197 -> administrative."""
    assert classify_denial_type(["PR-96"]) == DenialType.ADMINISTRATIVE
    assert classify_denial_type(["CO-197"]) == DenialType.ADMINISTRATIVE


def test_classify_denial_type_technical() -> None:
    """CO-18, CO-97 -> technical."""
    assert classify_denial_type(["CO-18"]) == DenialType.TECHNICAL
    assert classify_denial_type(["CO-97"]) == DenialType.TECHNICAL


def test_classify_denial_type_clinical() -> None:
    """CO-4 -> clinical."""
    assert classify_denial_type(["CO-4"]) == DenialType.CLINICAL
    assert classify_denial_type([]) == DenialType.CLINICAL


def test_classify_denial_type_mixed_codes() -> None:
    """When both clinical and technical codes present, technical takes precedence."""
    assert classify_denial_type(["CO-4", "CO-18"]) == DenialType.TECHNICAL
    assert classify_denial_type(["PR-96", "CO-18"]) == DenialType.TECHNICAL


def test_assess_appeal_viability_prior_auth_viable(examples_dir: Path) -> None:
    """PR-96 with documents -> viable."""
    encounter = _load_encounter(examples_dir, "encounter_004_denial_scenario.json")
    viable, summary = assess_appeal_viability(["PR-96"], encounter)
    assert viable is True
    assert "prior auth" in summary.lower() or "appeal" in summary.lower()


def test_assess_appeal_viability_duplicate_not_viable() -> None:
    """CO-18 duplicate -> not viable."""
    encounter = Encounter(
        encounter_id="E1",
        patient={"age": 30, "gender": "F", "zip": "10001"},
        insurance={"payer": "Aetna", "member_id": "M1", "plan_type": "PPO"},
        date="2026-01-01",
        type="office_visit",
        procedures=[],
        diagnoses=[],
        clinical_notes="",
        documents=[],
    )
    viable, summary = assess_appeal_viability(["CO-18"], encounter)
    assert viable is False
    assert "duplicate" in summary.lower()


def test_search_payer_policies_for_appeal_returns_list(examples_dir: Path) -> None:
    """search_payer_policies_for_appeal returns list of snippets (mock)."""
    snippets = search_payer_policies_for_appeal("Cigna", "29881")
    assert isinstance(snippets, list)


def test_generate_appeal_letter(examples_dir: Path) -> None:
    """generate_appeal_letter produces letter with encounter and denial info."""
    encounter = _load_encounter(examples_dir, "encounter_004_denial_scenario.json")
    denial_analysis = {
        "reason_codes": ["CO-4", "PR-96"],
        "denial_type": "administrative",
        "appeal_viable": True,
        "viability_summary": "Prior auth denial; viable for appeal.",
    }
    letter = generate_appeal_letter(encounter, denial_analysis, ["Policy snippet 1."])
    assert "ENC-004" in letter
    assert "Cigna" in letter
    assert "CO-4" in letter
    assert "PR-96" in letter
    assert "APPEAL LETTER" in letter or "Appeal" in letter


def test_assemble_appeal_packet(examples_dir: Path) -> None:
    """assemble_appeal_packet returns dict with cover_letter, supporting_documents, denial_summary."""
    encounter = _load_encounter(examples_dir, "encounter_004_denial_scenario.json")
    denial_analysis = {
        "reason_codes": ["CO-4"],
        "denial_type": "clinical",
        "appeal_viable": True,
        "viability_summary": "Viable.",
    }
    packet = assemble_appeal_packet(encounter, denial_analysis, "Cover letter text.")
    assert packet["encounter_id"] == "ENC-004"
    assert packet["claim_id"] == "CLM-004"
    assert packet["payer"] == "Cigna"
    assert packet["denial_summary"]["reason_codes"] == ["CO-4"]
    assert packet["cover_letter"] == "Cover letter text."
    assert "denial_letter.pdf" in packet["supporting_documents"]


def test_denial_reason_code_catalog_has_common_codes() -> None:
    """DENIAL_REASON_CODE_CATALOG includes CO-4, PR-96, CO-197."""
    assert "CO-4" in DENIAL_REASON_CODE_CATALOG
    assert "PR-96" in DENIAL_REASON_CODE_CATALOG
    assert "CO-197" in DENIAL_REASON_CODE_CATALOG
