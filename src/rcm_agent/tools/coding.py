"""Coding and charge capture tools: code suggestion, NCCI validation, missing charges, guidelines stub, fee schedule."""

from collections.abc import Callable
from typing import Any

from rcm_agent.models import Encounter, EncounterType
from rcm_agent.tools._types import (
    InvalidPair,
    MissingChargesResult,
    ModifierSuggestion,
    PerCodeReimbursement,
    ReimbursementResult,
    SuggestCodesResult,
    SuggestedCode,
    ValidateCodesResult,
)

# Keyword -> (ICD-10, CPT) suggestions for heuristic code suggestion. Subset for synthetic encounters.
_CLINICAL_TERM_TO_CODES: dict[str, list[tuple[str, str, str]]] = {
    "upper respiratory": [("J06.9", "Acute upper respiratory infection, unspecified", "99213")],
    "rhinorrhea": [("J06.9", "Acute upper respiratory infection, unspecified", "99213")],
    "sore throat": [("J02.9", "Acute pharyngitis, unspecified", "99213")],
    "knee pain": [("M25.561", "Pain in right knee", "73721")],
    "meniscal": [("M23.211", "Derangement of medial meniscus due to old tear, right knee", "29881")],
    "osteoarthritis": [("M16.11", "Unilateral primary osteoarthritis, right hip", "27130")],
    "hip": [("M16.11", "Unilateral primary osteoarthritis, right hip", "99223")],
    "abdominal pain": [("R10.9", "Unspecified abdominal pain", "99285")],
    "emergency": [("R10.9", "Unspecified abdominal pain", "99285")],
}

# NCCI edit pairs: (cpt1, cpt2) -> (allowed_with_modifier, modifier_suggestion).
# Subset of common bundling conflicts.
_NCCI_EDITS: dict[tuple[str, str], tuple[bool, str | None]] = {
    ("99213", "99214"): (False, None),  # Cannot bill two E&M same encounter without modifier
    ("73721", "73720"): (False, None),  # MRI with vs without contrast
    ("29881", "29880"): (False, None),  # Meniscectomy vs debridement
    ("27130", "99223"): (True, "57"),  # Procedure with E&M same day: modifier 57
}

# Fee schedule: (cpt_code, payer) -> amount. Fallback by cpt_code only.
_FEE_SCHEDULE: dict[tuple[str, str], float] = {
    ("99213", "Aetna"): 150.0,
    ("99213", "UnitedHealthcare"): 145.0,
    ("73721", "UnitedHealthcare"): 800.0,
    ("73721", "Aetna"): 780.0,
    ("99223", "Blue Cross Blue Shield"): 450.0,
    ("27130", "Blue Cross Blue Shield"): 25000.0,
    ("29881", "Cigna"): 3500.0,
    ("99285", "Anthem"): 650.0,
}
_DEFAULT_FEE: float = 200.0

# Coding guideline stub snippets keyed by query terms. Real RAG in Phase 4.
_MOCK_GUIDELINES: dict[str, list[str]] = {
    "e&m": ["Use time or MDM for E&M level selection. Document time or complexity."],
    "mri": ["MRI without contrast: use 73721. With contrast: 73720. Document medical necessity."],
    "arthroscopy": ["Knee arthroscopy: 29880 debridement, 29881 meniscectomy. Link to diagnosis."],
    "hip": ["Total hip arthroplasty 27130. Include implant and approach in documentation."],
}

# NCCI edit lookup: (cpt1, cpt2) -> snippet list for search_ncci_edits mock.
_MOCK_NCCI_SNIPPETS: dict[tuple[str, str], list[str]] = {
    ("99213", "99214"): [
        "NCCI: Cannot bill two E&M levels for same encounter without modifier; choose one or append modifier."
    ],
    ("73721", "73720"): [
        "NCCI: MRI with (73720) vs without (73721) contrast are mutually exclusive; do not bill both for same anatomic area."
    ],
    ("29881", "29880"): [
        "NCCI: Meniscectomy (29881) and debridement (29880) bundle; separate encounters or modifier if distinct."
    ],
    ("27130", "99223"): [
        "Modifier 57 may be required for same-day E&M (99223) with decision for major procedure (27130)."
    ],
}

# CMS requirements by topic for search_cms_requirements mock.
_MOCK_CMS_REQUIREMENTS: dict[str, list[str]] = {
    "prior auth": ["CMS prior authorization requirements may apply to certain services; check MAC/LCD."],
    "interoperability": ["CMS 2026 interoperability rules support prior auth APIs and electronic data exchange."],
    "coverage": ["Coverage determined by LCD/NCD and contract; document medical necessity."],
}


def suggest_codes(
    clinical_notes: str,
    encounter_type: str | EncounterType,
    existing_codes: dict[str, list[str]] | None = None,
) -> SuggestCodesResult:
    """
    Keyword-based ICD-10/CPT suggestion from clinical narrative.
    Returns suggested ICD-10-CM and CPT codes with confidence scores.
    """
    existing_codes = existing_codes or {}
    notes_lower = (clinical_notes or "").lower()
    suggested_icd: list[SuggestedCode] = []
    suggested_cpt: list[SuggestedCode] = []
    seen_icd: set[str] = set(existing_codes.get("icd", []))
    seen_cpt: set[str] = set(existing_codes.get("cpt", []))

    for term, code_tuples in _CLINICAL_TERM_TO_CODES.items():
        if term not in notes_lower:
            continue
        for icd, desc, cpt in code_tuples:
            if icd not in seen_icd:
                suggested_icd.append(SuggestedCode(code=icd, description=desc, confidence=0.85))
                seen_icd.add(icd)
            if cpt not in seen_cpt:
                suggested_cpt.append(SuggestedCode(code=cpt, description=desc, confidence=0.85))
                seen_cpt.add(cpt)

    # Prefer .value for Enum members so messages show "office_visit" not "EncounterType.office_visit"
    _val = getattr(encounter_type, "value", None)
    encounter_str = (
        _val if _val is not None else (encounter_type if isinstance(encounter_type, str) else str(encounter_type))
    )

    if not suggested_icd and not suggested_cpt:
        return SuggestCodesResult(
            icd_codes=[],
            cpt_codes=[],
            confidence=0.5,
            message=f"No keyword match for encounter type {encounter_str}; manual review recommended.",
        )

    return SuggestCodesResult(
        icd_codes=suggested_icd,
        cpt_codes=suggested_cpt,
        confidence=0.85 if (suggested_icd or suggested_cpt) else 0.5,
        message=f"Suggested {len(suggested_icd)} ICD code(s), {len(suggested_cpt)} CPT code(s) for encounter type {encounter_str}.",
    )


def validate_code_combinations(
    icd_codes: list[str],
    cpt_codes: list[str],
) -> ValidateCodesResult:
    """
    Check against hardcoded NCCI edit subset. Return valid/invalid pairs and modifier suggestions.
    """
    invalid_pairs: list[InvalidPair] = []
    modifier_suggestions: list[ModifierSuggestion] = []

    for i, cpt1 in enumerate(cpt_codes):
        for cpt2 in cpt_codes[i + 1 :]:
            key1, key2 = (cpt1, cpt2) if cpt1 <= cpt2 else (cpt2, cpt1)
            edit = _NCCI_EDITS.get((key1, key2)) or _NCCI_EDITS.get((key2, key1))
            if edit:
                allowed_with_mod, mod = edit
                if not allowed_with_mod:
                    invalid_pairs.append(
                        InvalidPair(cpt_1=key1, cpt_2=key2, reason="NCCI bundle; separate or modifier.")
                    )
                elif mod:
                    modifier_suggestions.append(
                        ModifierSuggestion(cpt=key2, modifier=mod, reason="Same-day procedure with E&M.")
                    )

    return ValidateCodesResult(
        valid=len(invalid_pairs) == 0,
        invalid_pairs=invalid_pairs,
        modifier_suggestions=modifier_suggestions,
    )


def _cpt_codes_to_set(cpt_codes: list[Any]) -> set[str]:
    """Normalize cpt_codes (list of dicts with 'code' or list of str) to set of code strings."""
    result: set[str] = set()
    for c in cpt_codes:
        if isinstance(c, dict) and "code" in c:
            result.add(str(c["code"]))
        elif isinstance(c, str):
            result.add(c)
    return result


def identify_missing_charges(
    encounter: Encounter,
    suggested_codes: SuggestCodesResult,
    effective_cpt_codes: list[str] | None = None,
) -> MissingChargesResult:
    """
    Compare documented procedures to suggested/coded procedures; flag missing modifiers and missing codes.
    When effective_cpt_codes is provided (e.g. from crew after merging suggestion with existing), use it
    for suggested_cpts; otherwise derive from suggested_codes["cpt_codes"].
    """
    documented_cpts = {p.code for p in encounter.procedures}
    if effective_cpt_codes is not None:
        suggested_cpts = set(effective_cpt_codes)
    else:
        suggested_cpts = _cpt_codes_to_set(suggested_codes.get("cpt_codes") or [])
    missing_codes = documented_cpts - suggested_cpts
    extra_suggested = suggested_cpts - documented_cpts

    flags: list[str] = []
    if missing_codes:
        flags.append(f"Documented procedure(s) not in suggested set: {sorted(missing_codes)}")
    if extra_suggested:
        if documented_cpts:
            flags.append(f"Suggested code(s) not documented in encounter: {sorted(extra_suggested)}")
        else:
            flags.append(f"Suggested codes with no documented procedure: {sorted(extra_suggested)}")

    cpt_list = list(documented_cpts) + list(suggested_cpts)
    if "27130" in cpt_list and "99223" in cpt_list:
        flags.append("Consider modifier 57 for same-day E&M with major procedure.")

    return MissingChargesResult(
        missing_codes=list(missing_codes),
        missing_charge_flags=flags,
        documented_procedures=list(documented_cpts),
        suggested_cpts=list(suggested_cpts),
    )


def search_coding_guidelines(
    query: str,
    backend: str | Callable[[str], list[str]] = "mock",
) -> list[str]:
    """
    Return coding guideline snippets for query. Default backend is mock (canned snippets).
    Phase 4 can inject a RAG backend by passing a callable(query) -> list[str].
    """
    if callable(backend):
        return backend(query)
    query_lower = query.lower()
    results: list[str] = []
    for key, snippets in _MOCK_GUIDELINES.items():
        if key in query_lower:
            results.extend(snippets)
    if not results:
        results = ["No guideline snippet on file; refer to current CPT/ICD-10 guidelines."]
    return results


def search_ncci_edits(
    cpt_code_1: str,
    cpt_code_2: str,
    backend: str | Callable[[str, str], list[str]] = "mock",
) -> list[str]:
    """
    Return NCCI edit snippets for a CPT code pair. Default backend is mock (canned snippets).
    RAG backend: callable(cpt_code_1, cpt_code_2) -> list[str].
    """
    if callable(backend):
        return backend(cpt_code_1.strip(), cpt_code_2.strip())
    key = (cpt_code_1.strip(), cpt_code_2.strip())
    key_rev = (key[1], key[0])
    snippets = _MOCK_NCCI_SNIPPETS.get(key) or _MOCK_NCCI_SNIPPETS.get(key_rev)
    if not snippets:
        return ["No NCCI edit snippet on file for this code pair; refer to NCCI PTP edits."]
    return snippets


def search_cms_requirements(
    topic: str,
    backend: str | Callable[[str], list[str]] = "mock",
) -> list[str]:
    """
    Return CMS regulation/requirement snippets for a topic. Default backend is mock (canned snippets).
    RAG backend: callable(topic) -> list[str].
    """
    if callable(backend):
        return backend(topic)
    topic_lower = topic.lower().strip()
    for key, snippets in _MOCK_CMS_REQUIREMENTS.items():
        if key in topic_lower:
            return snippets
    return ["No CMS requirement snippet on file for this topic; refer to CMS manuals and MAC guidance."]


def calculate_expected_reimbursement(cpt_codes: list[str], payer: str) -> ReimbursementResult:
    """
    Lookup hardcoded fee schedule. Return per-code and total expected reimbursement.
    """
    per_code: list[PerCodeReimbursement] = []
    total = 0.0
    for code in cpt_codes:
        amount = _FEE_SCHEDULE.get((code, payer))
        if amount is None:
            amount = _FEE_SCHEDULE.get((code, ""))
        if amount is None:
            amount = _DEFAULT_FEE
        per_code.append(PerCodeReimbursement(cpt_code=code, expected_amount=amount))
        total += amount
    return ReimbursementResult(
        payer=payer,
        per_code=per_code,
        total_expected=total,
    )
