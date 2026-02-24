"""TypedDict definitions for tool return shapes.

Each TypedDict documents the exact keys and value types returned by the
corresponding tool function, replacing untyped ``dict[str, Any]`` signatures.
"""

from __future__ import annotations

from typing import TypedDict

# ---------------------------------------------------------------------------
# Eligibility tools
# ---------------------------------------------------------------------------


class EligibilityResult(TypedDict):
    eligible: bool
    plan_name: str
    effective_date: str | None
    termination_date: str | None
    in_network: bool
    member_status: str
    date_of_service: str


class ProcedureBenefit(TypedDict):
    procedure_code: str
    covered: bool
    copay: float | None
    coinsurance_pct: float | None
    deductible_remaining: float | None


class BenefitsResult(TypedDict):
    payer: str
    member_id: str
    procedures: list[ProcedureBenefit]


class CoordinationOfBenefitsResult(TypedDict):
    has_secondary: bool
    secondary_note: str | None
    payer: str
    plan_type: str


# ---------------------------------------------------------------------------
# Prior-auth tools
# ---------------------------------------------------------------------------


class ClinicalIndicatorsResult(TypedDict):
    diagnoses: list[str]
    symptoms: list[str]
    medical_necessity_indicators: list[str]
    summary: str


class AuthPacket(TypedDict):
    encounter_id: str
    patient: dict[str, object]
    payer: str
    member_id: str
    date_of_service: str
    procedure_codes: list[str]
    procedure_descriptions: list[str]
    diagnoses: list[str]
    clinical_indicators: ClinicalIndicatorsResult
    clinical_justification: str
    policy_references: dict[str, list[str]]
    clinical_notes_excerpt: str


class AuthSubmitResult(TypedDict):
    auth_id: str
    status: str
    submitted_at: str
    message: str


class AuthStatusResult(TypedDict):
    auth_id: str
    status: str
    decision: str | None
    decision_date: str | None
    message: str


# ---------------------------------------------------------------------------
# Coding tools
# ---------------------------------------------------------------------------


class SuggestedCode(TypedDict):
    code: str
    description: str
    confidence: float


class SuggestCodesResult(TypedDict):
    icd_codes: list[SuggestedCode]
    cpt_codes: list[SuggestedCode]
    confidence: float
    message: str


class InvalidPair(TypedDict):
    cpt_1: str
    cpt_2: str
    reason: str


class ModifierSuggestion(TypedDict):
    cpt: str
    modifier: str
    reason: str


class ValidateCodesResult(TypedDict):
    valid: bool
    invalid_pairs: list[InvalidPair]
    modifier_suggestions: list[ModifierSuggestion]


class MissingChargesResult(TypedDict):
    missing_codes: list[str]
    missing_charge_flags: list[str]
    documented_procedures: list[str]
    suggested_cpts: list[str]


class PerCodeReimbursement(TypedDict):
    cpt_code: str
    expected_amount: float


class ReimbursementResult(TypedDict):
    payer: str
    per_code: list[PerCodeReimbursement]
    total_expected: float


# ---------------------------------------------------------------------------
# Denial tools (return primitives / tuples, no TypedDict needed except
# the denial_analysis dict used by appeal tools)
# ---------------------------------------------------------------------------


class DenialAnalysis(TypedDict):
    reason_codes: list[str]
    denial_type: str
    appeal_viable: bool
    viability_summary: str


# ---------------------------------------------------------------------------
# Appeal tools
# ---------------------------------------------------------------------------


class DenialSummary(TypedDict):
    reason_codes: list[str]
    denial_type: str | None
    appeal_viable: bool | None
    viability_summary: str | None


class AppealPacket(TypedDict):
    encounter_id: str
    claim_id: str | None
    payer: str
    member_id: str
    date_of_service: str
    denial_summary: DenialSummary
    procedure_codes: list[str]
    procedure_descriptions: list[str]
    diagnosis_codes: list[str]
    cover_letter: str
    supporting_documents: list[str]


# ---------------------------------------------------------------------------
# Claims submission tools
# ---------------------------------------------------------------------------


class ClaimLineItem(TypedDict):
    line_number: int
    cpt_code: str
    description: str
    icd_pointers: list[str]
    modifiers: list[str]
    units: int
    charge_amount: float


class CleanClaimData(TypedDict):
    """837-style claim payload assembled from encounter and coding data."""

    encounter_id: str
    billing_provider_npi: str
    payer: str
    member_id: str
    patient: dict[str, object]
    date_of_service: str
    place_of_service: str
    icd_codes: list[str]
    cpt_codes: list[str]
    modifiers: list[str]
    line_items: list[ClaimLineItem]
    total_charges: float
    authorization_number: str | None


class ScrubError(TypedDict):
    field: str
    code: str
    message: str


class ScrubResult(TypedDict):
    clean: bool
    errors: list[ScrubError]
    warnings: list[ScrubError]
    edit_actions: list[str]


class SubmitClaimResult(TypedDict):
    claim_id: str | None
    status: str
    submitted_at: str
    message: str
    tracking_number: str | None


class RemitAdjustment(TypedDict):
    group_code: str
    reason_code: str
    amount: float
    description: str


class RemitStatusResult(TypedDict):
    claim_id: str | None
    status: str
    paid_amount: float | None
    allowed_amount: float | None
    patient_responsibility: float | None
    adjustments: list[RemitAdjustment]
    check_number: str | None
    remit_date: str | None
    message: str | None
