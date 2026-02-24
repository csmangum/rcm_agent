"""Prior authorization tools: clinical extraction, policy stub, auth packet assembly, submit/poll via backend."""

import re
from collections.abc import Callable
from typing import Any

from rcm_agent.integrations.registry import get_prior_auth_backend
from rcm_agent.models import Encounter
from rcm_agent.tools._types import (
    AuthPacket,
    AuthStatusResult,
    AuthSubmitResult,
    ClinicalIndicatorsResult,
)

# Keywords/phrases that indicate medical necessity and clinical indicators (heuristic extraction).
_MEDICAL_NECESSITY_KEYWORDS = (
    "failed",
    "conservative",
    "therapy",
    "pt",
    "physical therapy",
    "nsaids",
    "ordered",
    "evaluate",
    "meniscal",
    "tear",
    "pain",
    "chronic",
    "mri",
    "surgery",
    "surgical",
    "arthroscopy",
    "osteoarthritis",
    "replacement",
)
_DIAGNOSIS_PATTERN = re.compile(r"\b([A-Z][0-9]{2}\.[0-9A-Z]{0,4})\b", re.I)
_SYMPTOM_KEYWORDS = ("pain", "swelling", "stiffness", "limited range", "weakness", "numbness")

# Canned policy snippets keyed by (payer, procedure_code). Real RAG in Phase 4.
_MOCK_POLICY_SNIPPETS: dict[tuple[str, str], list[str]] = {
    ("UnitedHealthcare", "73721"): [
        "MRI knee without contrast requires prior auth for non-emergent indications.",
        "Document failed conservative treatment (PT, NSAIDs) and clinical indication for MRI.",
    ],
    ("Aetna", "73721"): [
        "Aetna requires prior authorization for MRI knee. Submit clinical justification.",
    ],
    ("Cigna", "29881"): [
        "Knee arthroscopy with meniscectomy requires prior auth. Include operative plan.",
    ],
    ("Blue Cross Blue Shield", "27130"): [
        "Total hip arthroplasty requires prior auth. Document osteoarthritis severity and failed non-surgical care.",
    ],
}


def extract_clinical_indicators(clinical_notes: str) -> ClinicalIndicatorsResult:
    """
    Keyword/regex extraction of diagnoses, symptoms, failed treatments, medical necessity indicators.
    Heuristic default; no LLM needed for POC.
    """
    notes_lower = (clinical_notes or "").lower()
    diagnoses = list(set(_DIAGNOSIS_PATTERN.findall(clinical_notes or "")))
    symptoms = [s for s in _SYMPTOM_KEYWORDS if s in notes_lower]
    medical_necessity = [k for k in _MEDICAL_NECESSITY_KEYWORDS if k in notes_lower]
    return ClinicalIndicatorsResult(
        diagnoses=diagnoses,
        symptoms=symptoms,
        medical_necessity_indicators=medical_necessity,
        summary=f"Extracted {len(diagnoses)} diagnosis codes, {len(symptoms)} symptoms, {len(medical_necessity)} necessity indicators.",
    )


def search_payer_policies(
    payer: str,
    procedure_code: str,
    backend: str | Callable[[str, str], list[str]] = "mock",
) -> list[str]:
    """
    Return policy snippets for (payer, procedure_code). Default backend is mock (canned snippets).
    Phase 4 can inject a RAG backend by passing a callable(payer, procedure_code) -> list[str].
    """
    if callable(backend):
        return backend(payer, procedure_code)
    key = (payer.strip(), procedure_code.strip())
    return _MOCK_POLICY_SNIPPETS.get(key, ["No specific policy snippet on file; submit per plan requirements."])


def assemble_auth_packet(
    encounter: Encounter,
    clinical_indicators: ClinicalIndicatorsResult,
    policy_matches: dict[str, list[str]],
) -> AuthPacket:
    """
    Assemble structured prior auth request: patient info, procedure, clinical justification, policy refs.
    """
    notes_excerpt = (encounter.clinical_notes or "")[:500]
    summary = clinical_indicators.get("summary", "")
    clinical_justification = (summary + " " + notes_excerpt).strip() or "No clinical justification extracted."
    return AuthPacket(
        encounter_id=encounter.encounter_id,
        patient=encounter.patient.model_dump(),
        payer=encounter.insurance.payer,
        member_id=encounter.insurance.member_id,
        date_of_service=encounter.date,
        procedure_codes=[p.code for p in encounter.procedures],
        procedure_descriptions=[p.description for p in encounter.procedures],
        diagnoses=[d.code for d in encounter.diagnoses],
        clinical_indicators=clinical_indicators,
        clinical_justification=clinical_justification,
        policy_references=policy_matches,
        clinical_notes_excerpt=notes_excerpt,
    )


def submit_auth_request(auth_packet: AuthPacket | dict[str, Any]) -> AuthSubmitResult:
    """Submit prior auth request via configured backend."""
    result: dict[str, Any] = get_prior_auth_backend().submit_auth_request(dict(auth_packet))
    return AuthSubmitResult(
        auth_id=result["auth_id"],
        status=result["status"],
        submitted_at=result["submitted_at"],
        message=result.get("message", ""),
    )


def poll_auth_status(auth_id: str) -> AuthStatusResult:
    """Poll prior auth status via configured backend."""
    result: dict[str, Any] = get_prior_auth_backend().poll_auth_status(auth_id)
    return AuthStatusResult(
        auth_id=result["auth_id"],
        status=result["status"],
        decision=result.get("decision"),
        decision_date=result.get("decision_date"),
        message=result.get("message", ""),
    )
