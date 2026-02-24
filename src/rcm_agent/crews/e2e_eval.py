"""End-to-end evaluation: run full pipeline on synthetic encounters and measure outcomes.

Runs process_encounter_multi_stage for each encounter, collects outcomes, and computes
metrics: pipeline success rate, router alignment, prior auth coverage, coding/claim readiness.
Uses OpenRouter (OPENAI_API_KEY, OPENAI_API_BASE, OPENAI_MODEL_NAME) from .env for LLM calls.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rcm_agent.crews.main_crew import process_encounter_multi_stage
from rcm_agent.crews.router_eval import _default_examples_dir, load_encounters_from_dir
from rcm_agent.models import Encounter, EncounterOutput, EncounterStatus, RcmStage

logger = logging.getLogger(__name__)

# Failure statuses that halt the pipeline
_FAILURE_STATUSES = frozenset({
    EncounterStatus.NOT_ELIGIBLE,
    EncounterStatus.AUTH_DENIED,
    EncounterStatus.CLAIM_DENIED,
})

# "Clean" outcomes: pipeline completed successfully
_CLEAN_STATUSES = frozenset({
    EncounterStatus.ELIGIBLE,
    EncounterStatus.AUTH_APPROVED,
    EncounterStatus.CODED,
    EncounterStatus.CLAIM_SUBMITTED,
    EncounterStatus.CLAIM_ACCEPTED,
})


@dataclass
class E2ERecord:
    """Per-encounter e2e evaluation result."""

    encounter_id: str
    stages_run: list[str]
    final_status: str
    escalated: bool
    prior_auth_needed: bool
    prior_auth_produced: bool
    prior_auth_approved: bool | None
    reached_claims: bool
    router_aligned: bool | None
    success: bool = False
    error: str | None = None
    artifacts: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "encounter_id": self.encounter_id,
            "stages_run": self.stages_run,
            "final_status": self.final_status,
            "escalated": self.escalated,
            "prior_auth_needed": self.prior_auth_needed,
            "prior_auth_produced": self.prior_auth_produced,
            "prior_auth_approved": self.prior_auth_approved,
            "reached_claims": self.reached_claims,
            "router_aligned": self.router_aligned,
            "success": self.success,
            "error": self.error,
            "artifacts": self.artifacts,
        }


@dataclass
class E2ESummary:
    """Aggregate e2e evaluation metrics."""

    total: int = 0
    pipeline_successes: int = 0
    escalations: int = 0
    prior_auth_needed_count: int = 0
    prior_auth_produced_count: int = 0
    prior_auth_approved_count: int = 0
    reached_claims_count: int = 0
    router_aligned_count: int = 0
    golden_compared_count: int = 0
    records: list[E2ERecord] = field(default_factory=list)

    @property
    def pipeline_success_rate(self) -> float:
        return self.pipeline_successes / self.total if self.total > 0 else 0.0

    @property
    def prior_auth_coverage_rate(self) -> float:
        return (
            self.prior_auth_produced_count / self.prior_auth_needed_count
            if self.prior_auth_needed_count > 0
            else 1.0
        )

    @property
    def claim_readiness_rate(self) -> float:
        return self.reached_claims_count / self.total if self.total > 0 else 0.0

    @property
    def router_alignment_rate(self) -> float:
        return (
            self.router_aligned_count / self.golden_compared_count
            if self.golden_compared_count > 0
            else 0.0
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "pipeline_successes": self.pipeline_successes,
            "pipeline_success_rate": round(self.pipeline_success_rate, 3),
            "escalations": self.escalations,
            "prior_auth_needed": self.prior_auth_needed_count,
            "prior_auth_produced": self.prior_auth_produced_count,
            "prior_auth_approved": self.prior_auth_approved_count,
            "prior_auth_coverage_rate": round(self.prior_auth_coverage_rate, 3),
            "reached_claims": self.reached_claims_count,
            "claim_readiness_rate": round(self.claim_readiness_rate, 3),
            "router_aligned": self.router_aligned_count,
            "golden_compared": self.golden_compared_count,
            "router_alignment_rate": round(self.router_alignment_rate, 3),
            "records": [r.to_dict() for r in self.records],
        }


def _load_golden(golden_path: Path | None) -> dict[str, dict[str, Any]]:
    """Load golden expectations from JSON file."""
    if golden_path is None or not golden_path.is_file():
        return {}
    try:
        with open(golden_path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to load golden data from %s: %s", golden_path, e)
        return {}


def _extract_prior_auth_from_outputs(outputs: list[EncounterOutput]) -> tuple[bool, bool | None]:
    """Return (produced, approved). approved is None if not applicable."""
    for out in outputs:
        if out.stage == RcmStage.PRIOR_AUTHORIZATION:
            raw = out.raw_result or {}
            auth_num = raw.get("authorization_number") or raw.get("auth_id")
            produced = bool(auth_num)
            if out.status == EncounterStatus.AUTH_APPROVED:
                return (True, True)
            if out.status == EncounterStatus.AUTH_DENIED:
                return (True, False)
            return (produced, None)
    return (False, None)


def _encounter_needs_prior_auth(encounter: Encounter) -> bool:
    """Check if encounter has procedure codes requiring prior auth."""
    from rcm_agent.config import get_auth_required_procedures

    auth_cpt = get_auth_required_procedures()
    procedure_codes = {p.code for p in encounter.procedures}
    return bool(procedure_codes & auth_cpt)


def _compute_router_alignment(
    stages_run: list[str],
    golden: dict[str, Any] | None,
) -> bool | None:
    """Compare stages_run to golden expected_stages. None if no golden."""
    if not golden or "expected_stages" not in golden:
        return None
    expected = set(golden.get("expected_stages", []))
    actual = set(stages_run)
    # Allow extra stages (pipeline may add CLAIMS_SUBMISSION after coding)
    # but require all expected stages to be present
    return expected.issubset(actual)


def run_e2e_evaluation(
    encounters: list[Encounter] | None = None,
    examples_dir: str | Path | None = None,
    golden_path: str | Path | None = None,
    output_path: str | Path | None = None,
    output_dir: str | Path | None = None,
) -> E2ESummary:
    """
    Run e2e evaluation: full pipeline on each encounter, collect outcomes, compute metrics.

    Args:
        encounters: Pre-loaded encounters. If None, load from examples_dir.
        examples_dir: Directory with encounter JSONs (used if encounters is None).
        golden_path: Path to golden.json with expected stages/outcomes.
        output_path: Path to write JSON report.
        output_dir: If set, write report to output_dir/e2e_eval.json.

    Returns:
        E2ESummary with per-encounter records and aggregate metrics.
    """
    # Ensure config is loaded (load_dotenv via settings)
    from rcm_agent.config import settings  # noqa: F401

    if encounters is None:
        if examples_dir is None:
            examples_dir = _default_examples_dir()
        examples_dir = Path(examples_dir)
        logger.info("Loading encounters from %s", examples_dir)
        encounters = load_encounters_from_dir(examples_dir)

    if not encounters:
        logger.warning("No encounters to evaluate")
        return E2ESummary()

    golden = _load_golden(Path(golden_path) if golden_path else Path("data/eval/golden.json"))

    summary = E2ESummary()
    summary.total = len(encounters)

    for encounter in encounters:
        try:
            outputs = process_encounter_multi_stage(encounter)
        except Exception as e:
            logger.exception("Pipeline failed for %s", encounter.encounter_id)
            summary.records.append(
                E2ERecord(
                    encounter_id=encounter.encounter_id,
                    stages_run=[],
                    final_status="ERROR",
                    escalated=False,
                    prior_auth_needed=_encounter_needs_prior_auth(encounter),
                    prior_auth_produced=False,
                    prior_auth_approved=None,
                    reached_claims=False,
                    router_aligned=None,
                    success=False,
                    error=str(e),
                )
            )
            continue

        stages_run = [o.stage.value for o in outputs]
        last = outputs[-1] if outputs else None
        final_status = last.status.value if last else "UNKNOWN"
        escalated = last is not None and last.stage == RcmStage.HUMAN_ESCALATION

        prior_auth_needed = _encounter_needs_prior_auth(encounter)
        prior_auth_produced, prior_auth_approved = _extract_prior_auth_from_outputs(outputs)

        reached_claims = any(
            o.stage == RcmStage.CLAIMS_SUBMISSION for o in outputs
        ) or final_status in ("CLAIM_SUBMITTED", "CLAIM_ACCEPTED")

        # Pipeline success: completed without fatal error and without inappropriate escalation
        is_success = (
            not escalated
            and last is not None
            and last.status not in _FAILURE_STATUSES
            and (
                last.status in _CLEAN_STATUSES
                or last.stage == RcmStage.DENIAL_APPEAL
            )
        )

        router_aligned = _compute_router_alignment(stages_run, golden.get(encounter.encounter_id))

        artifacts: dict[str, Any] = {}
        for o in outputs:
            if o.stage == RcmStage.PRIOR_AUTHORIZATION:
                artifacts["authorization_number"] = (o.raw_result or {}).get(
                    "authorization_number"
                ) or (o.raw_result or {}).get("auth_id")
            if o.stage == RcmStage.CODING_CHARGE_CAPTURE:
                artifacts["suggested_codes"] = (o.raw_result or {}).get("suggested_codes")
            if o.stage == RcmStage.CLAIMS_SUBMISSION:
                artifacts["claim_id"] = (o.raw_result or {}).get("claim_id")

        record = E2ERecord(
            encounter_id=encounter.encounter_id,
            stages_run=stages_run,
            final_status=final_status,
            escalated=escalated,
            prior_auth_needed=prior_auth_needed,
            prior_auth_produced=prior_auth_produced,
            prior_auth_approved=prior_auth_approved,
            reached_claims=reached_claims,
            router_aligned=router_aligned,
            success=is_success,
            artifacts=artifacts,
        )
        summary.records.append(record)

        if is_success:
            summary.pipeline_successes += 1
        if escalated:
            summary.escalations += 1
        if prior_auth_needed:
            summary.prior_auth_needed_count += 1
        if prior_auth_produced:
            summary.prior_auth_produced_count += 1
        if prior_auth_approved is True:
            summary.prior_auth_approved_count += 1
        if reached_claims:
            summary.reached_claims_count += 1
        if router_aligned is not None:
            summary.golden_compared_count += 1
            if router_aligned:
                summary.router_aligned_count += 1

    out = output_path or (Path(output_dir) / "e2e_eval.json" if output_dir else None)
    if out:
        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(summary.to_dict(), f, indent=2)
        logger.info("E2E eval report written to %s", out)
        # Write markdown summary alongside JSON
        md_path = out.with_suffix(".md")
        _write_markdown_summary(summary, md_path)

    return summary


def _write_markdown_summary(summary: E2ESummary, path: Path) -> None:
    """Write a short markdown summary of e2e eval results."""
    lines = [
        "# E2E Evaluation Summary",
        "",
        f"- **Total encounters:** {summary.total}",
        f"- **Pipeline success rate:** {summary.pipeline_success_rate:.1%}",
        f"- **Escalations:** {summary.escalations}",
        f"- **Prior auth coverage:** {summary.prior_auth_produced_count}/{summary.prior_auth_needed_count}",
        f"- **Claim readiness:** {summary.reached_claims_count}/{summary.total}",
        f"- **Router alignment (vs golden):** {summary.router_aligned_count}/{summary.golden_compared_count}",
        "",
        "## Per-encounter",
        "",
        "| Encounter | Stages | Status | Success |",
        "|-----------|--------|--------|---------|",
    ]
    for r in summary.records:
        success = "✓" if r.success else "✗"
        lines.append(f"| {r.encounter_id} | {', '.join(r.stages_run)} | {r.final_status} | {success} |")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    logger.info("E2E eval markdown summary written to %s", path)
