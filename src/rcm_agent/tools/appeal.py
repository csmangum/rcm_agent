"""Appeal tools: RAG search for appeal, appeal letter draft, appeal packet assembly."""

from typing import Any, Callable

from rcm_agent.models import Encounter
from rcm_agent.rag import get_payer_policy_backend
from rcm_agent.tools.prior_auth import search_payer_policies


def search_payer_policies_for_appeal(
    payer: str,
    procedure_code: str,
    backend: str | Callable[[str, str], list[str]] | None = None,
) -> list[str]:
    """
    Return policy snippets for appeal context (payer, procedure).
    Reuses RAG/prior_auth search; query tuned for appeal and medical necessity.
    """
    if backend is None:
        backend = get_payer_policy_backend() or "mock"
    snippets = search_payer_policies(payer, procedure_code, backend=backend)
    # Optional: append appeal-specific RAG query if we had a separate appeal index
    return snippets


def generate_appeal_letter(
    encounter: Encounter,
    denial_analysis: dict[str, Any],
    policy_snippets: list[str],
) -> str:
    """
    Produce draft appeal letter: patient/encounter summary, denial codes, clinical justification, policy references.
    Template + f-strings; no LLM for POC.
    """
    reason_codes = denial_analysis.get("reason_codes") or []
    denial_type = denial_analysis.get("denial_type") or "clinical"
    appeal_viable = denial_analysis.get("appeal_viable", True)
    viability_summary = denial_analysis.get("viability_summary") or ""

    proc_codes = [p.code for p in encounter.procedures]
    proc_descs = [p.description for p in encounter.procedures]
    diag_codes = [d.code for d in encounter.diagnoses]
    payer = encounter.insurance.payer
    member_id = encounter.insurance.member_id

    policy_ref = "\n".join(f"  - {s[:200]}..." if len(s) > 200 else f"  - {s}" for s in policy_snippets[:5]) if policy_snippets else "  (No policy snippets retrieved.)"

    letter = f"""
APPEAL LETTER – Claim Denial

Payer: {payer}
Member ID: {member_id}
Encounter ID: {encounter.encounter_id}
Date of Service: {encounter.date}

DENIAL REASON CODES: {", ".join(reason_codes) or "Not specified"}
CLASSIFICATION: {denial_type}
APPEAL VIABILITY: {"Viable" if appeal_viable else "Not recommended"}
{viability_summary}

SERVICES REQUESTED:
Procedure codes: {", ".join(proc_codes)}
Descriptions: {", ".join(proc_descs)}
Diagnosis codes: {", ".join(diag_codes)}

CLINICAL JUSTIFICATION:
{ (encounter.clinical_notes or "No clinical notes provided.")[:800] }

POLICY / COVERAGE REFERENCES:
{policy_ref}

We request reconsideration of the denial and approval of the above services based on the clinical documentation and policy references provided. Supporting documents are attached.

Please contact our office with any questions.
"""
    return letter.strip()


def assemble_appeal_packet(
    encounter: Encounter,
    denial_analysis: dict[str, Any],
    letter_text: str,
) -> dict[str, Any]:
    """
    Assemble appeal packet: cover letter, supporting docs list, denial summary, procedure/diagnosis codes.
    """
    return {
        "encounter_id": encounter.encounter_id,
        "claim_id": (encounter.denial_info.claim_id if encounter.denial_info else None),
        "payer": encounter.insurance.payer,
        "member_id": encounter.insurance.member_id,
        "date_of_service": encounter.date,
        "denial_summary": {
            "reason_codes": denial_analysis.get("reason_codes") or [],
            "denial_type": denial_analysis.get("denial_type"),
            "appeal_viable": denial_analysis.get("appeal_viable"),
            "viability_summary": denial_analysis.get("viability_summary"),
        },
        "procedure_codes": [p.code for p in encounter.procedures],
        "procedure_descriptions": [p.description for p in encounter.procedures],
        "diagnosis_codes": [d.code for d in encounter.diagnoses],
        "cover_letter": letter_text,
        "supporting_documents": list(encounter.documents),
    }
