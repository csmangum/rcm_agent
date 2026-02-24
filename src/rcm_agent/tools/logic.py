"""Deterministic escalation (HITL) checks for RCM encounters."""

from rcm_agent.config import get_escalation_config
from rcm_agent.models import Encounter, EncounterStatus, EscalationOutput, RcmStage

# Oncology-related keywords in clinical notes
_ONCOLOGY_KEYWORDS = ("oncology", "cancer", "tumor", "malignant", "carcinoma", "neoplasm")


def _is_oncology_icd(code: str) -> bool:
    """True if ICD-10-CM code is in oncology range C00-C96 (malignant) or D00-D09 (in situ)."""
    code = code.upper().strip()
    if not code or len(code) < 3:
        return False
    # C00-C96: malignant neoplasms (including C7A/C7B neuroendocrine tumors)
    if code[0] == "C":
        if code[1:3].isdigit():
            return 0 <= int(code[1:3]) <= 96
        # Handle C7A and C7B (malignant neuroendocrine tumors)
        if code[1:3] in ("7A", "7B"):
            return True
    # D00-D09: in situ neoplasms
    return code[0] == "D" and code[1] == "0" and code[2] in "0123456789"


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
    if confidence is not None and confidence < config.confidence_threshold:
        reasons.append(f"Confidence score {confidence:.2f} below threshold {config.confidence_threshold}")

    # 2. High dollar value
    if estimated_charges is not None and estimated_charges > config.high_value_threshold:
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
