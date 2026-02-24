"""Pydantic domain models for encounters and RCM workflows."""

from enum import Enum
from typing import Any, TypedDict

try:
    from enum import StrEnum
except ImportError:
    # Python < 3.11
    class StrEnum(str, Enum):
        """String enum (enum.StrEnum exists from 3.11 onward)."""
        pass

from pydantic import BaseModel, Field


class PipelineContext(TypedDict, total=False):
    """Optional context from earlier pipeline stages (e.g. coding, prior auth)."""

    coding_result: dict[str, Any]
    authorization_number: str


class RcmStage(StrEnum):
    """RCM workflow stage (replaces ClaimType)."""

    INTAKE = "INTAKE"
    ELIGIBILITY_VERIFICATION = "ELIGIBILITY_VERIFICATION"
    PRIOR_AUTHORIZATION = "PRIOR_AUTHORIZATION"
    CODING_CHARGE_CAPTURE = "CODING_CHARGE_CAPTURE"
    CLAIMS_SUBMISSION = "CLAIMS_SUBMISSION"
    DENIAL_APPEAL = "DENIAL_APPEAL"
    HUMAN_ESCALATION = "HUMAN_ESCALATION"


class EncounterStatus(StrEnum):
    """Encounter lifecycle status."""

    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    ELIGIBLE = "ELIGIBLE"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    AUTH_APPROVED = "AUTH_APPROVED"
    AUTH_DENIED = "AUTH_DENIED"
    CODED = "CODED"
    CLAIM_SUBMITTED = "CLAIM_SUBMITTED"
    CLAIM_ACCEPTED = "CLAIM_ACCEPTED"
    CLAIM_DENIED = "CLAIM_DENIED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    ESCALATED = "ESCALATED"


class EncounterType(StrEnum):
    """Type of encounter. Values use snake_case to match common EMR/EDI conventions."""

    outpatient_procedure = "outpatient_procedure"
    inpatient = "inpatient"
    office_visit = "office_visit"
    emergency = "emergency"


class PriorAuthStatus(StrEnum):
    """Prior authorization request status."""

    PENDING = "pending"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    DENIED = "denied"


class PriorAuthDecision(StrEnum):
    """Prior authorization decision outcome."""

    APPROVED = "approved"
    DENIED = "denied"
    PENDING = "pending"


class ClaimStatus(StrEnum):
    """Claim submission status."""

    DRAFT = "draft"
    SUBMITTED = "submitted"
    ACCEPTED = "accepted"
    DENIED = "denied"
    PAID = "paid"


class Patient(BaseModel):
    """De-identified patient demographics."""

    age: int
    gender: str
    zip: str


class Insurance(BaseModel):
    """Insurance information."""

    payer: str
    member_id: str
    plan_type: str


class ProcedureCode(BaseModel):
    """Procedure (CPT/HCPCS) code and description."""

    code: str
    description: str


class DiagnosisCode(BaseModel):
    """Diagnosis (ICD) code and description."""

    code: str
    description: str


class DenialInfo(BaseModel):
    """Structured denial payload for denial/appeal workflow."""

    claim_id: str | None = None
    reason_codes: list[str] = Field(default_factory=list)
    denial_date: str | None = None


class Encounter(BaseModel):
    """Encounter input (replaces ClaimInput)."""

    encounter_id: str
    patient: Patient
    insurance: Insurance
    date: str
    type: EncounterType
    procedures: list[ProcedureCode]
    diagnoses: list[DiagnosisCode]
    clinical_notes: str
    documents: list[str]
    denial_info: DenialInfo | None = None


class EncounterOutput(BaseModel):
    """Result of processing an encounter (replaces ClaimOutput)."""

    encounter_id: str
    stage: RcmStage
    status: EncounterStatus
    actions_taken: list[str] = Field(default_factory=list)
    artifacts: list[str] = Field(default_factory=list)
    message: str = ""
    raw_result: dict[str, Any] = Field(default_factory=dict)


class PriorAuthRequest(BaseModel):
    """Prior authorization request lifecycle."""

    auth_id: str
    encounter_id: str
    payer: str
    procedure_codes: list[str]
    clinical_justification: str
    status: PriorAuthStatus
    submitted_at: str
    decision: PriorAuthDecision | None = None
    decision_date: str | None = None


class ClaimSubmission(BaseModel):
    """Claim submission lifecycle."""

    claim_id: str
    encounter_id: str
    payer: str
    total_charges: float
    icd_codes: list[str]
    cpt_codes: list[str]
    modifiers: list[str] = Field(default_factory=list)
    status: ClaimStatus
    submitted_at: str


class EscalationOutput(BaseModel):
    """Human escalation result with RCM-specific reasons."""

    encounter_id: str
    reasons: list[str]
    stage: RcmStage
    status: EncounterStatus
    message: str = ""
