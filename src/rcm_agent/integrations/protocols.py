"""Protocols (interfaces) for external system integration.

Each protocol defines the contract for one external capability. Mock implementations
live in adapters; real FHIR/EDI implementations can be added later and swapped via config.
"""

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class EligibilityBackend(Protocol):
    """Interface for payer eligibility and benefits verification.

    Request/response shapes (dicts) are described below; implementations may
    add extra keys. Used for mock payer APIs, FHIR Coverage/ExplanationOfBenefit,
    or EDI 270/271.
    """

    def check_member_eligibility(
        self,
        payer: str,
        member_id: str,
        date_of_service: str,
    ) -> dict[str, Any]:
        """Check whether the member is eligible for coverage on the given date.

        Returns a dict with at least:
            - eligible: bool
            - plan_name: str
            - effective_date: str | None
            - termination_date: str | None
            - in_network: bool
            - member_status: str (e.g. "active", "terminated")
            - date_of_service: str
        """
        ...

    def verify_benefits(
        self,
        payer: str,
        member_id: str,
        procedure_codes: list[str],
    ) -> dict[str, Any]:
        """Verify benefits (covered, copay, coinsurance, deductible) per procedure code.

        Returns a dict with at least:
            - payer: str
            - member_id: str
            - procedures: list[dict] with keys procedure_code, covered, copay,
              coinsurance_pct, deductible_remaining (per procedure)
        """
        ...


@runtime_checkable
class PriorAuthBackend(Protocol):
    """Interface for prior authorization submit and status polling.

    Request/response shapes align with mock prior_auth tools; real implementations
    may map to FHIR Task/RequestGroup or payer-specific APIs.
    """

    def submit_auth_request(self, auth_packet: dict[str, Any]) -> dict[str, Any]:
        """Submit a prior authorization request.

        Args:
            auth_packet: Structured request (encounter_id, patient, payer, member_id,
                date_of_service, procedure_codes, diagnoses, clinical_justification, etc.)

        Returns a dict with at least:
            - auth_id: str
            - status: str (e.g. "submitted")
            - submitted_at: str (ISO datetime)
            - message: str (optional)
        """
        ...

    def poll_auth_status(self, auth_id: str) -> dict[str, Any]:
        """Poll the status of a prior authorization by auth_id.

        Returns a dict with at least:
            - auth_id: str
            - status: str (e.g. "pending", "approved", "denied")
            - decision: str | None ("approved" | "denied" | None)
            - decision_date: str | None (ISO datetime, when present)
            - message: str (optional)
        """
        ...


@runtime_checkable
class ClaimsBackend(Protocol):
    """Placeholder interface for claims submission and remittance.

    Stub for future coding/claims integration (e.g. submit claim, get remit).
    Real implementations would map to EDI 837/835 or FHIR Claim/ClaimResponse.
    """

    def submit_claim(self, claim_payload: dict[str, Any]) -> dict[str, Any]:
        """Submit a claim (stub).

        Intended request: encounter/claim data. Intended response: claim_id, status, etc.
        Implementations may raise or return a stub response until implemented.
        """
        ...

    def get_remit(self, claim_id: str) -> dict[str, Any]:
        """Retrieve remittance for a claim (stub).

        Intended response: payment info, adjustments, CARC/RARC, etc.
        Implementations may raise or return a stub response until implemented.
        """
        ...
