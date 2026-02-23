"""Denial analysis tools: parse reason codes, classify denial type, assess appeal viability."""

import re
from typing import Any

from rcm_agent.models import Encounter

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


def parse_denial_reason_codes(encounter: Encounter) -> list[str]:
    """
    Return list of denial reason codes from encounter.
    Uses encounter.denial_info.reason_codes if present; otherwise parses clinical_notes.
    """
    if encounter.denial_info and encounter.denial_info.reason_codes:
        return list(encounter.denial_info.reason_codes)
    notes = encounter.clinical_notes or ""
    found = _REASON_CODE_PATTERN.findall(notes)
    return list(dict.fromkeys(f.upper() for f in found))


class DenialType:
    """Denial classification: clinical, administrative, technical."""

    CLINICAL = "clinical"
    ADMINISTRATIVE = "administrative"
    TECHNICAL = "technical"


def classify_denial_type(reason_codes: list[str]) -> str:
    """
    Classify denial into clinical (medical necessity/coverage), administrative (prior auth, timely filing), or technical (coding, duplicate).
    Rule-based; no LLM.
    """
    if not reason_codes:
        return DenialType.CLINICAL
    codes_upper = [c.upper() for c in reason_codes]
    # Technical: duplicate, coding issues
    if any(c in codes_upper for c in ("CO-18", "CO-97", "CO-16")):
        return DenialType.TECHNICAL
    # Administrative: prior auth, timely filing
    if any(c in codes_upper for c in ("PR-96", "PR-1", "CO-197", "CO-29")):
        return DenialType.ADMINISTRATIVE
    # Clinical: not covered, medical necessity (CO-4, etc.)
    return DenialType.CLINICAL


def assess_appeal_viability(
    denial_type: str,
    reason_codes: list[str],
    encounter: Encounter,
) -> tuple[bool, str]:
    """
    Determine if appeal is viable and return (viable, summary).
    PR-96/prior auth -> viable with documentation; CO-4 -> maybe; duplicate -> not viable.
    """
    codes_upper = [c.upper() for c in reason_codes]
    if not reason_codes:
        return True, "No reason codes; recommend manual review for appeal viability."

    # Duplicate / technical filing issues: usually not viable for clinical appeal
    if "CO-18" in codes_upper:
        return False, "Duplicate claim; resubmission or correction may be more appropriate than appeal."
    if "CO-29" in codes_upper:
        return False, "Timely filing exceeded; appeal unlikely to succeed."

    # Prior auth not on file: viable if we have documentation
    if any(c in codes_upper for c in ("PR-96", "PR-1", "CO-197")):
        has_docs = bool(encounter.documents) or bool((encounter.clinical_notes or "").strip())
        if has_docs:
            return True, "Prior auth denial; viable for appeal with supporting documentation (auth on file, clinical notes)."
        return True, "Prior auth denial; appeal viable but gather prior auth approval and clinical documentation."

    # CO-4 / not covered: often medical necessity appeal
    if "CO-4" in codes_upper:
        return True, "Procedure not covered; appeal viable with medical necessity and policy documentation."

    return True, "Recommend appeal with full clinical and policy documentation."
