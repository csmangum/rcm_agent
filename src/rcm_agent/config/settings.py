"""RCM-specific settings loaded from environment and YAML config."""

import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()

_CONFIG_DIR = Path(__file__).resolve().parent
_ROUTING_RULES_PATH = _CONFIG_DIR / "routing_rules.yaml"
_logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _load_routing_rules() -> dict[str, Any]:
    """Load routing_rules.yaml; returns empty dict if missing or on error."""
    if not _ROUTING_RULES_PATH.is_file():
        return {}
    try:
        with open(_ROUTING_RULES_PATH, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError) as e:
        _logger.warning("Failed to load routing_rules.yaml: %s; using fallbacks.", e)
        return {}


def reload_routing_rules() -> dict[str, Any]:
    """Force-reload routing rules (clears LRU cache). Useful after config changes."""
    _load_routing_rules.cache_clear()
    return _load_routing_rules()


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
        confidence_threshold=float(os.environ.get("ESCALATION_CONFIDENCE_THRESHOLD", "0.85")),
        high_value_threshold=float(os.environ.get("ESCALATION_HIGH_VALUE_THRESHOLD", "5000")),
        oncology_flag=_parse_bool(os.environ.get("ESCALATION_ONCOLOGY_FLAG"), True),
        incomplete_data_flag=_parse_bool(os.environ.get("ESCALATION_INCOMPLETE_DATA_FLAG"), True),
    )


def _rules() -> dict[str, Any]:
    return _load_routing_rules()


DEFAULT_AUTH_REQUIRED_CPT = {"73721", "70450", "72148", "29881"}


def _cpt_charge_amounts_from_yaml() -> dict[str, float]:
    raw = _rules().get("cpt_charge_amounts", {})
    return {str(k): float(v) for k, v in raw.items()} if raw else {}


def _get_cpt_charge_amounts() -> dict[str, float]:
    yaml_vals = _cpt_charge_amounts_from_yaml()
    if yaml_vals:
        return yaml_vals
    return {
        "99213": 150.00,
        "99223": 450.00,
        "73721": 800.00,
        "70450": 400.00,
        "72148": 600.00,
        "29881": 3500.00,
        "27130": 25000.00,
        "99285": 650.00,
    }


def get_cpt_charge_amounts() -> dict[str, float]:
    """CPT charge amounts from YAML config (recomputed on each call, picks up reload)."""
    return _get_cpt_charge_amounts()


def _get_default_charge() -> float:
    return float(_rules().get("default_charge", 200.00))


def get_default_charge() -> float:
    """Default charge amount from YAML config (recomputed on each call, picks up reload)."""
    return _get_default_charge()


def get_auth_required_procedures() -> set[str]:
    """CPT codes requiring prior authorization (env var > YAML > hardcoded default)."""
    raw = os.environ.get("AUTH_REQUIRED_CPT_CODES")
    if raw and raw.strip():
        return {code.strip() for code in raw.split(",") if code.strip()}
    yaml_list = _rules().get("auth_required_cpt")
    if yaml_list:
        return {str(c) for c in yaml_list}
    return set(DEFAULT_AUTH_REQUIRED_CPT)


def get_rag_config() -> dict[str, Any]:
    """RAG backend selection and ChromaDB path. Backend: 'mock' or 'rag'."""
    default_chroma = Path.home() / "medicare_rag" / "data" / "chroma"
    raw = os.environ.get("RCM_RAG_CHROMA_DIR", "").strip()
    chroma_dir = Path(raw).expanduser() if raw else default_chroma
    backend = (os.environ.get("RCM_RAG_BACKEND") or "mock").strip().lower()
    if backend not in ("mock", "rag"):
        backend = "mock"
    return {"backend": backend, "chroma_dir": chroma_dir}


def get_integrations_config() -> dict[str, Any]:
    """Eligibility, prior-auth, and claims backend selection; optional base URL for 'http' backend."""
    eligibility = (os.environ.get("ELIGIBILITY_BACKEND") or "mock").strip().lower()
    prior_auth = (os.environ.get("PRIOR_AUTH_BACKEND") or "mock").strip().lower()
    claims = (os.environ.get("CLAIMS_BACKEND") or "mock").strip().lower()
    mock_server_url = (os.environ.get("RCM_MOCK_SERVER_URL") or "http://localhost:8000").strip().rstrip("/")
    return {
        "eligibility": eligibility,
        "prior_auth": prior_auth,
        "claims": claims,
        "mock_server_url": mock_server_url,
    }


def get_payer_config() -> dict[str, dict[str, Any]]:
    """Payer-specific rules loaded from YAML config with hardcoded fallback."""
    yaml_payers = _rules().get("payer_rules")
    if yaml_payers:
        return dict(yaml_payers)
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


def get_heuristic_keywords() -> dict[str, list[str]]:
    """Heuristic routing keywords from YAML config."""
    result = _rules().get(
        "heuristic_keywords",
        {
            "denial_appeal": ["denial", "appeal", "denied"],
            "eligibility": ["lapsed", "termination", "terminated", "eligibility"],
        },
    )
    return {k: list(v) for k, v in result.items()}


def get_multi_stage_sequences() -> dict[str, list[str]]:
    """Multi-stage routing sequences from YAML config."""
    result = _rules().get(
        "multi_stage_sequences",
        {
            "ELIGIBILITY_VERIFICATION": ["PRIOR_AUTHORIZATION", "CODING_CHARGE_CAPTURE"],
            "PRIOR_AUTHORIZATION": ["CODING_CHARGE_CAPTURE"],
            "CODING_CHARGE_CAPTURE": ["CLAIMS_SUBMISSION"],
        },
    )
    return {k: list(v) for k, v in result.items()}


def get_router_llm_config() -> dict[str, Any]:
    """LLM router configuration from YAML config."""
    defaults = {"confidence_threshold": 0.9, "model": "gpt-4o-mini"}
    yaml_cfg = _rules().get("router_llm", {})
    defaults.update(yaml_cfg or {})
    return defaults
