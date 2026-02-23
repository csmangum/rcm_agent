"""Encounter router: heuristic and optional LLM-based classification into RcmStage."""

import os

from pydantic import BaseModel

from rcm_agent.config import get_auth_required_procedures
from rcm_agent.models import Encounter, RcmStage


class RouterResult(BaseModel):
    """Result of routing an encounter to an RCM stage."""

    stage: RcmStage
    confidence: float
    reasoning: str


def _llm_router_enabled() -> bool:
    """True if LLM-based router fallback is enabled (default: false)."""
    raw = os.environ.get("RCM_ROUTER_LLM_ENABLED", "false")
    return raw.strip().lower() in ("true", "1", "yes", "on")


def classify_encounter(encounter: Encounter) -> RouterResult:
    """
    Classify encounter into RcmStage using deterministic heuristics.
    Order of checks: denial/appeal -> eligibility -> prior auth -> coding (default).
    """
    notes_lower = (encounter.clinical_notes or "").lower()
    procedure_codes = {p.code for p in encounter.procedures}
    auth_cpt = get_auth_required_procedures()

    # DENIAL_APPEAL: structured denial_info present or notes mention denial/appeal
    if encounter.denial_info is not None:
        return RouterResult(
            stage=RcmStage.DENIAL_APPEAL,
            confidence=1.0,
            reasoning="Structured denial_info present; route to denial/appeal.",
        )
    if "denial" in notes_lower or "appeal" in notes_lower or "denied" in notes_lower:
        return RouterResult(
            stage=RcmStage.DENIAL_APPEAL,
            confidence=1.0,
            reasoning="Clinical notes mention denial or appeal; route to denial/appeal.",
        )

    # ELIGIBILITY_VERIFICATION: lapsed, termination, or eligibility issues
    if any(
        kw in notes_lower
        for kw in ("lapsed", "termination", "terminated", "eligibility")
    ):
        return RouterResult(
            stage=RcmStage.ELIGIBILITY_VERIFICATION,
            confidence=1.0,
            reasoning="Notes indicate eligibility or coverage issues; route to eligibility verification.",
        )

    # PRIOR_AUTHORIZATION: procedure in auth-required list
    if procedure_codes & auth_cpt:
        return RouterResult(
            stage=RcmStage.PRIOR_AUTHORIZATION,
            confidence=1.0,
            reasoning=f"Procedure code(s) {sorted(procedure_codes & auth_cpt)} require prior auth; route to prior authorization.",
        )

    # CODING_CHARGE_CAPTURE: default when procedures and diagnoses present
    if encounter.procedures and encounter.diagnoses:
        return RouterResult(
            stage=RcmStage.CODING_CHARGE_CAPTURE,
            confidence=0.95,
            reasoning="Procedures and diagnoses present; route to coding/charge capture.",
        )

    # Low-confidence default
    return RouterResult(
        stage=RcmStage.CODING_CHARGE_CAPTURE,
        confidence=0.7,
        reasoning="Default to coding/charge capture; incomplete or ambiguous encounter data.",
    )


def route_encounter(encounter: Encounter) -> RouterResult:
    """
    Route encounter: run heuristics first; optionally call LLM router when
    heuristic confidence is below threshold (disabled by default).
    """
    result = classify_encounter(encounter)
    if result.confidence < 0.9 and _llm_router_enabled():
        # Phase 2: LLM router not implemented; keep heuristic result.
        # In Phase 3+, load RouterCrew and call llm_classify_encounter(encounter).
        pass
    return result
