"""Deterministic escalation (HITL) checks for RCM encounters."""

from rcm_agent.config import get_escalation_config
from rcm_agent.models import Encounter, EncounterStatus, EscalationOutput, RcmStage

# Oncology-related keywords in clinical notes
_ONCOLOGY_KEYWORDS = ("oncology", "cancer", "tumor", "malignant", "carcinoma", "neoplasm")


def _is_oncology_icd(code: str) -> bool:
    """True if ICD-10 code is in oncology range C00-C96 or D00-D09."""
    code = code.upper().strip()
    if not code:
        return False
    # C00-C96: malignant neoplasms
    if code.startswith("C"):
        return True
    # D00-D09: in situ neoplasms
    if code.startswith("D0"):
        return True
    return False


def _notes_suggest_oncology(clinical_notes: str | None) -> bool:
    """True if clinical notes contain oncology-related keywords."""
    if not clinical_notes:
        return False
    lower = clinical_notes.lower()
    return any(kw in lower for kw in _ONCOLOGY_KEYWORDS)


def check_escalation(
    encounter: Encounter,
    *,
    confidence: float | None = None,
    estimated_charges: float | None = None,
) -> EscalationOutput | None:
    """
    Run deterministic escalation checks. Returns None if no escalation;
    returns EscalationOutput with all triggered reasons otherwise.
    """
    config = get_escalation_config()
    reasons: list[str] = []

    # 1. Low confidence
    if config.confidence_threshold and confidence is not None:
        if confidence < config.confidence_threshold:
            reasons.append(
                f"Confidence score {confidence:.2f} below threshold {config.confidence_threshold}"
            )

    # 2. High dollar value
    if config.high_value_threshold and estimated_charges is not None:
        if estimated_charges > config.high_value_threshold:
            reasons.append(
                f"Estimated charges ${estimated_charges:,.0f} exceed threshold ${config.high_value_threshold:,.0f}"
            )

    # 3. Oncology flag
    if config.oncology_flag:
        if any(_is_oncology_icd(d.code) for d in encounter.diagnoses):
            reasons.append("Oncology-related ICD code(s) present; escalation required")
        elif _notes_suggest_oncology(encounter.clinical_notes):
            reasons.append("Clinical notes suggest oncology case; escalation required")

    # 4. Incomplete data
    if config.incomplete_data_flag:
        if not (encounter.clinical_notes or "").strip():
            reasons.append("Missing or empty clinical notes")
        if not encounter.documents:
            reasons.append("No documents attached")

    if not reasons:
        return None

    message = "Human review required: " + "; ".join(reasons)
    return EscalationOutput(
        encounter_id=encounter.encounter_id,
        reasons=reasons,
        stage=RcmStage.HUMAN_ESCALATION,
        status=EncounterStatus.NEEDS_REVIEW,
        message=message,
    )
