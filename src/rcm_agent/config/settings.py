"""RCM-specific settings loaded from environment."""

import os
from typing import Any

from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Load .env if present (no-op if file missing)
load_dotenv()


class EscalationConfig(BaseModel):
    """Configurable escalation (HITL) thresholds."""

    confidence_threshold: float = Field(default=0.85, ge=0.0, le=1.0)
    high_value_threshold: float = Field(default=5000.0, ge=0.0)
    oncology_flag: bool = True
    incomplete_data_flag: bool = True


def _parse_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in ("true", "1", "yes", "on")


def get_escalation_config() -> EscalationConfig:
    """Load escalation config from environment."""
    return EscalationConfig(
        confidence_threshold=float(
            os.environ.get("ESCALATION_CONFIDENCE_THRESHOLD", "0.85")
        ),
        high_value_threshold=float(
            os.environ.get("ESCALATION_HIGH_VALUE_THRESHOLD", "5000")
        ),
        oncology_flag=_parse_bool(
            os.environ.get("ESCALATION_ONCOLOGY_FLAG"), True
        ),
        incomplete_data_flag=_parse_bool(
            os.environ.get("ESCALATION_INCOMPLETE_DATA_FLAG"), True
        ),
    )


DEFAULT_AUTH_REQUIRED_CPT = {"73721", "70450", "72148", "29881"}


def get_auth_required_procedures() -> set[str]:
    """List of CPT codes requiring prior authorization (from env or default)."""
    raw = os.environ.get("AUTH_REQUIRED_CPT_CODES")
    if not raw or not raw.strip():
        return set(DEFAULT_AUTH_REQUIRED_CPT)
    return {code.strip() for code in raw.split(",") if code.strip()}


def get_payer_config() -> dict[str, dict[str, Any]]:
    """Payer-specific rules (hardcoded for MVP; externalize later)."""
    return {
        "UnitedHealthcare": {
            "auth_required_cpt_override": [],
            "common_denial_codes": ["CO-4", "PR-96"],
        },
        "Aetna": {
            "auth_required_cpt_override": [],
            "common_denial_codes": ["CO-4", "CO-197"],
        },
        "Blue Cross Blue Shield": {
            "auth_required_cpt_override": [],
            "common_denial_codes": ["CO-4", "PR-96"],
        },
        "Cigna": {
            "auth_required_cpt_override": [],
            "common_denial_codes": ["CO-4", "PR-96"],
        },
        "Anthem": {
            "auth_required_cpt_override": [],
            "common_denial_codes": ["CO-4", "CO-197"],
        },
    }
