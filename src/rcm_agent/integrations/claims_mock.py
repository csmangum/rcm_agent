"""Mock implementation of ClaimsBackend with in-memory claim store.

Simulates 837 submission, scrubbing edits, and 835 remittance retrieval.
Used as the default backend for claims submission crews and CLI.
"""

import uuid
from datetime import datetime, timezone
from typing import Any

# Required fields for a clean claim (simplified 837-P).
_REQUIRED_FIELDS = (
    "encounter_id",
    "payer",
    "member_id",
    "billing_provider_npi",
    "date_of_service",
    "icd_codes",
    "cpt_codes",
    "total_charges",
)

# Payer-specific scrubbing rules: payer -> list of (check_fn, error_dict).
_PAYER_SCRUB_RULES: dict[str, list[dict[str, Any]]] = {
    "Anthem": [
        {
            "field": "member_id",
            "code": "ANT-001",
            "message": "Anthem requires 12-character member ID.",
            "check": lambda v: isinstance(v, str) and len(v) >= 12,
        }
    ],
}

# Mock fee-schedule for remittance calculation (cpt -> allowed amount).
_ALLOWED_AMOUNTS: dict[str, float] = {
    "99213": 128.50,
    "99223": 410.00,
    "73721": 720.00,
    "70450": 360.00,
    "72148": 540.00,
    "29881": 3200.00,
    "27130": 22500.00,
    "99285": 580.00,
}
_DEFAULT_ALLOWED = 180.00


class ClaimsMock:
    """ClaimsBackend implementation using an in-memory dict keyed by claim_id."""

    def __init__(self) -> None:
        self._store: dict[str, dict[str, Any]] = {}

    def reset(self) -> None:
        """Clear the claim store (for tests)."""
        self._store.clear()

    def scrub_claim(self, claim_payload: dict[str, Any]) -> dict[str, Any]:
        errors: list[dict[str, str]] = []
        warnings: list[dict[str, str]] = []
        edit_actions: list[str] = []

        for field in _REQUIRED_FIELDS:
            val = claim_payload.get(field)
            if val is None or (isinstance(val, (str, list)) and len(val) == 0):
                errors.append(
                    {"field": field, "code": "MISSING", "message": f"Required field '{field}' is missing or empty."}
                )

        icd_codes = claim_payload.get("icd_codes") or []
        cpt_codes = claim_payload.get("cpt_codes") or []
        if icd_codes and cpt_codes:
            pass  # Real scrubber would check LCD/NCD medical-necessity edits here.

        payer = claim_payload.get("payer", "")
        for rule in _PAYER_SCRUB_RULES.get(payer, []):
            val = claim_payload.get(rule["field"])
            if not rule["check"](val):
                errors.append({"field": rule["field"], "code": rule["code"], "message": rule["message"]})

        total = claim_payload.get("total_charges")
        if isinstance(total, (int, float)) and total <= 0:
            warnings.append(
                {"field": "total_charges", "code": "ZERO_CHARGE", "message": "Total charges are zero or negative."}
            )

        dos = claim_payload.get("date_of_service", "")
        if dos and dos > datetime.now(timezone.utc).strftime("%Y-%m-%d"):
            warnings.append(
                {"field": "date_of_service", "code": "FUTURE_DOS", "message": "Date of service is in the future."}
            )

        modifiers = claim_payload.get("modifiers") or []
        # Suggested edit for audit; assembly (assemble_clean_claim) already adds modifier 57 when applicable.
        if "27130" in cpt_codes and "99223" in cpt_codes and "57" not in modifiers:
            edit_actions.append("AUTO_ADD_MOD57: Added modifier 57 for same-day E&M with major procedure.")

        return {
            "clean": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "edit_actions": edit_actions,
        }

    def submit_claim(self, claim_payload: dict[str, Any]) -> dict[str, Any]:
        claim_id = f"CLM-{uuid.uuid4().hex[:8].upper()}"
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        tracking = f"TRK-{uuid.uuid4().hex[:6].upper()}"

        self._store[claim_id] = {
            "claim_payload": claim_payload,
            "status": "accepted",
            "submitted_at": now,
            "tracking_number": tracking,
        }
        return {
            "claim_id": claim_id,
            "status": "accepted",
            "submitted_at": now,
            "message": "Claim accepted for adjudication (mock).",
            "tracking_number": tracking,
        }

    def get_remit(self, claim_id: str) -> dict[str, Any]:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        record = self._store.get(claim_id)
        if record is None:
            return {
                "claim_id": claim_id,
                "status": "not_found",
                "paid_amount": None,
                "allowed_amount": None,
                "patient_responsibility": None,
                "adjustments": [],
                "check_number": None,
                "remit_date": None,
                "message": "Claim not found in mock store.",
            }

        payload = record.get("claim_payload", {})
        cpt_codes = payload.get("cpt_codes", [])
        total_allowed = sum(_ALLOWED_AMOUNTS.get(c, _DEFAULT_ALLOWED) for c in cpt_codes)
        total_charges = payload.get("total_charges", total_allowed)

        co_adjustment = max(total_charges - total_allowed, 0.0)
        coinsurance = round(total_allowed * 0.20, 2)
        paid = round(total_allowed - coinsurance, 2)

        adjustments: list[dict[str, Any]] = []
        if co_adjustment > 0:
            adjustments.append(
                {
                    "group_code": "CO",
                    "reason_code": "45",
                    "amount": round(co_adjustment, 2),
                    "description": "Charge exceeds fee schedule/maximum allowable.",
                }
            )
        adjustments.append(
            {
                "group_code": "PR",
                "reason_code": "2",
                "amount": coinsurance,
                "description": "Coinsurance amount (20%).",
            }
        )

        record["status"] = "paid"
        check_number = f"CHK-{uuid.uuid4().hex[:6].upper()}"

        return {
            "claim_id": claim_id,
            "status": "paid",
            "paid_amount": paid,
            "allowed_amount": round(total_allowed, 2),
            "patient_responsibility": coinsurance,
            "adjustments": adjustments,
            "check_number": check_number,
            "remit_date": now,
            "message": "Claim paid (mock remittance).",
        }
