"""Denial analysis tools: parse reason codes, classify denial type, assess appeal viability."""

import re

from rcm_agent.models import Encounter
from rcm_agent.observability.logging import get_logger

# CARC/remit reason code catalog: code -> short description
DENIAL_REASON_CODE_CATALOG: dict[str, str] = {
    "CO-4": "Procedure/product not covered by payer",
    "CO-197": "Prior authorization missing or invalid",
    "PR-96": "Prior authorization not on file",
    "PR-1": "Prior authorization required",
    "CO-18": "Duplicate claim/service",
    "CO-29": "Time limit for filing has expired",
    "CO-97": "Payment adjusted for missing/incomplete/invalid diagnosis code",
    "CO-16": "Claim lacks information needed for adjudication",
}

# Regex to find reason codes in text (e.g. "CO-4", "PR-96")
_REASON_CODE_PATTERN = re.compile(r"\b(CO-\d+|PR-\d+)\b", re.I)

logger = get_logger(__name__)


def parse_denial_reason_codes(encounter: Encounter) -> list[str]:
    """
    Return list of denial reason codes from encounter.
    Uses encounter.denial_info.reason_codes if present; otherwise parses clinical_notes.
    """
    if encounter.denial_info and encounter.denial_info.reason_codes:
        codes = list(encounter.denial_info.reason_codes)
    else:
        notes = encounter.clinical_notes or ""
        found = _REASON_CODE_PATTERN.findall(notes)
        codes = list(dict.fromkeys(f.upper() for f in found))
    logger.info(
        "Tool call: parse_denial_reason_codes",
        action="tool_call",
        tool="parse_denial_reason_codes",
        reason_codes=codes,
    )
    return codes


class DenialType:
    """Denial classification: clinical, administrative, technical."""

    CLINICAL = "clinical"
    ADMINISTRATIVE = "administrative"
    TECHNICAL = "technical"


def classify_denial_type(reason_codes: list[str]) -> str:
    """
    Classify denial into clinical (medical necessity/coverage), administrative (prior auth, timely filing), or technical (coding, duplicate).
    Rule-based; no LLM.

    When multiple code types exist, precedence is: technical (CO-18, CO-97, CO-16), then administrative (PR-96, PR-1, CO-197, CO-29), then clinical. One classification is returned per encounter for analytics and messaging.
    """
    if not reason_codes:
        denial_type = DenialType.CLINICAL
    else:
        codes_upper = [c.upper() for c in reason_codes]
        # Technical: duplicate, coding issues
        if any(c in codes_upper for c in ("CO-18", "CO-97", "CO-16")):
            denial_type = DenialType.TECHNICAL
        # Administrative: prior auth, timely filing
        elif any(c in codes_upper for c in ("PR-96", "PR-1", "CO-197", "CO-29")):
            denial_type = DenialType.ADMINISTRATIVE
        # Clinical: not covered, medical necessity (CO-4, etc.)
        else:
            denial_type = DenialType.CLINICAL
    logger.info(
        "Tool call: classify_denial_type",
        action="tool_call",
        tool="classify_denial_type",
        denial_type=denial_type,
    )
    return denial_type


def assess_appeal_viability(
    reason_codes: list[str],
    encounter: Encounter,
) -> tuple[bool, str]:
    """
    Determine if appeal is viable and return (viable, summary).
    PR-96/prior auth -> viable with documentation; CO-4 -> maybe; duplicate -> not viable.
    """
    codes_upper = [c.upper() for c in reason_codes]
    if not reason_codes:
        viable, summary = True, "No reason codes; recommend manual review for appeal viability."
        logger.info(
            "Tool call: assess_appeal_viability",
            action="tool_call",
            tool="assess_appeal_viability",
            viable=viable,
            summary=summary,
        )
        return viable, summary

    # Duplicate / technical filing issues: usually not viable for clinical appeal
    if "CO-18" in codes_upper:
        viable, summary = False, "Duplicate claim; resubmission or correction may be more appropriate than appeal."
    elif "CO-29" in codes_upper:
        viable, summary = False, "Timely filing exceeded; appeal unlikely to succeed."
    # Prior auth not on file: viable if we have documentation
    elif any(c in codes_upper for c in ("PR-96", "PR-1", "CO-197")):
        has_docs = bool(encounter.documents) or bool((encounter.clinical_notes or "").strip())
        if has_docs:
            viable, summary = (
                True,
                "Prior auth denial; viable for appeal with supporting documentation (auth on file, clinical notes).",
            )
        else:
            viable, summary = True, "Prior auth denial; appeal viable but gather prior auth approval and clinical documentation."
    # CO-4 / not covered: often medical necessity appeal
    elif "CO-4" in codes_upper:
        viable, summary = True, "Procedure not covered; appeal viable with medical necessity and policy documentation."
    else:
        viable, summary = True, "Recommend appeal with full clinical and policy documentation."

    logger.info(
        "Tool call: assess_appeal_viability",
        action="tool_call",
        tool="assess_appeal_viability",
        viable=viable,
        summary=summary,
    )
    return viable, summary
