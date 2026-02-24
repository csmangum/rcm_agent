"""Router evaluation: compare heuristic vs LLM classifications across encounters.

Runs both routing strategies on a set of encounters, logs disagreements, and
produces a summary report useful for tuning heuristic rules and LLM prompts.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rcm_agent.crews.router import (
    MultiStageRouterResult,
    classify_encounter,
    classify_encounter_multi_stage,
    llm_classify_encounter,
)
from rcm_agent.models import Encounter, RcmStage

logger = logging.getLogger(__name__)


@dataclass
class EvalRecord:
    """Single encounter evaluation comparing heuristic and LLM routing."""

    encounter_id: str
    heuristic_stage: str
    heuristic_confidence: float
    heuristic_reasoning: str
    heuristic_stages_multi: list[str]
    llm_stage: str | None
    llm_confidence: float | None
    llm_reasoning: str | None
    llm_stages_multi: list[str]
    agrees: bool
    agrees_multi: bool
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "encounter_id": self.encounter_id,
            "heuristic_stage": self.heuristic_stage,
            "heuristic_confidence": self.heuristic_confidence,
            "heuristic_reasoning": self.heuristic_reasoning,
            "heuristic_stages_multi": self.heuristic_stages_multi,
            "llm_stage": self.llm_stage,
            "llm_confidence": self.llm_confidence,
            "llm_reasoning": self.llm_reasoning,
            "llm_stages_multi": self.llm_stages_multi,
            "agrees": self.agrees,
            "agrees_multi": self.agrees_multi,
            "notes": self.notes,
        }


@dataclass
class EvalSummary:
    """Aggregate evaluation results."""

    total: int = 0
    agreements: int = 0
    disagreements: int = 0
    llm_failures: int = 0
    multi_stage_agreements: int = 0
    multi_stage_disagreements: int = 0
    records: list[EvalRecord] = field(default_factory=list)

    @property
    def agreement_rate(self) -> float:
        evaluated = self.total - self.llm_failures
        return self.agreements / evaluated if evaluated > 0 else 0.0

    @property
    def multi_stage_agreement_rate(self) -> float:
        evaluated = self.total - self.llm_failures
        return self.multi_stage_agreements / evaluated if evaluated > 0 else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "agreements": self.agreements,
            "disagreements": self.disagreements,
            "llm_failures": self.llm_failures,
            "agreement_rate": round(self.agreement_rate, 3),
            "multi_stage_agreements": self.multi_stage_agreements,
            "multi_stage_disagreements": self.multi_stage_disagreements,
            "multi_stage_agreement_rate": round(self.multi_stage_agreement_rate, 3),
            "records": [r.to_dict() for r in self.records],
        }


def evaluate_encounter(encounter: Encounter) -> EvalRecord:
    """Run both heuristic and LLM classification on a single encounter."""
    heuristic = classify_encounter(encounter)
    heuristic_multi = classify_encounter_multi_stage(encounter)
    llm_result: MultiStageRouterResult | None = None

    try:
        llm_result = llm_classify_encounter(encounter)
    except Exception:
        logger.exception("LLM classification failed for %s", encounter.encounter_id)

    if llm_result is None:
        return EvalRecord(
            encounter_id=encounter.encounter_id,
            heuristic_stage=heuristic.stage.value,
            heuristic_confidence=heuristic.confidence,
            heuristic_reasoning=heuristic.reasoning,
            heuristic_stages_multi=[s.value for s in heuristic_multi.stages],
            llm_stage=None,
            llm_confidence=None,
            llm_reasoning=None,
            llm_stages_multi=[],
            agrees=False,
            agrees_multi=False,
            notes="LLM classification unavailable or failed",
        )

    llm_primary_stage = llm_result.primary_stage.value
    agrees = heuristic.stage.value == llm_primary_stage

    h_set = set(s.value for s in heuristic_multi.stages)
    l_set = set(s.value for s in llm_result.stages)
    agrees_multi = h_set == l_set

    notes = ""
    if not agrees:
        notes = (
            f"DISAGREEMENT: heuristic={heuristic.stage.value}({heuristic.confidence:.2f}) "
            f"vs llm={llm_primary_stage}({llm_result.primary_confidence:.2f})"
        )
        logger.warning(
            "Router eval disagreement for %s: %s", encounter.encounter_id, notes
        )
    if not agrees_multi:
        multi_note = (
            f"MULTI-STAGE DISAGREEMENT: heuristic={sorted(h_set)} "
            f"vs llm={sorted(l_set)}"
        )
        if notes:
            notes += "; " + multi_note
        else:
            notes = multi_note
        logger.warning(
            "Router eval multi-stage disagreement for %s: %s",
            encounter.encounter_id,
            multi_note,
        )

    return EvalRecord(
        encounter_id=encounter.encounter_id,
        heuristic_stage=heuristic.stage.value,
        heuristic_confidence=heuristic.confidence,
        heuristic_reasoning=heuristic.reasoning,
        heuristic_stages_multi=[s.value for s in heuristic_multi.stages],
        llm_stage=llm_primary_stage,
        llm_confidence=llm_result.primary_confidence,
        llm_reasoning=llm_result.reasoning,
        llm_stages_multi=[s.value for s in llm_result.stages],
        agrees=agrees,
        agrees_multi=agrees_multi,
        notes=notes,
    )


def evaluate_encounters(encounters: list[Encounter]) -> EvalSummary:
    """Evaluate a list of encounters and return aggregate summary."""
    summary = EvalSummary()

    for encounter in encounters:
        record = evaluate_encounter(encounter)
        summary.records.append(record)
        summary.total += 1

        if record.llm_stage is None:
            summary.llm_failures += 1
        elif record.agrees:
            summary.agreements += 1
        else:
            summary.disagreements += 1

        if record.llm_stage is not None:
            if record.agrees_multi:
                summary.multi_stage_agreements += 1
            else:
                summary.multi_stage_disagreements += 1

    return summary


def load_encounters_from_dir(directory: str | Path) -> list[Encounter]:
    """Load all encounter JSON files from a directory."""
    d = Path(directory)
    encounters = []
    for path in sorted(d.glob("encounter_*.json")):
        with open(path, encoding="utf-8") as f:
            enc = Encounter.model_validate(json.load(f))
            encounters.append(enc)
    return encounters


def run_evaluation(
    examples_dir: str | Path | None = None,
    output_path: str | Path | None = None,
) -> EvalSummary:
    """
    Run router evaluation across synthetic encounters.

    Args:
        examples_dir: directory containing encounter JSON files.
                      Defaults to data/examples.
        output_path: optional path to write JSON report.

    Returns:
        EvalSummary with per-encounter records and aggregate stats.
    """
    if examples_dir is None:
        examples_dir = Path(__file__).resolve().parent.parent.parent.parent / "data" / "examples"
    examples_dir = Path(examples_dir)

    logger.info("Loading encounters from %s", examples_dir)
    encounters = load_encounters_from_dir(examples_dir)
    logger.info("Evaluating %d encounters", len(encounters))

    summary = evaluate_encounters(encounters)

    logger.info(
        "Evaluation complete: %d total, %d agree, %d disagree, %d LLM failures (%.1f%% agreement)",
        summary.total,
        summary.agreements,
        summary.disagreements,
        summary.llm_failures,
        summary.agreement_rate * 100,
    )

    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(summary.to_dict(), f, indent=2)
        logger.info("Evaluation report written to %s", output_path)

    return summary
