"""Unit tests for config/settings."""

import pytest

from rcm_agent.config import (
    EscalationConfig,
    get_auth_required_procedures,
    get_escalation_config,
    get_payer_config,
)


def test_get_escalation_config_returns_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """get_escalation_config returns correct default values."""
    for key in (
        "ESCALATION_CONFIDENCE_THRESHOLD",
        "ESCALATION_HIGH_VALUE_THRESHOLD",
        "ESCALATION_ONCOLOGY_FLAG",
        "ESCALATION_INCOMPLETE_DATA_FLAG",
    ):
        monkeypatch.delenv(key, raising=False)
    config = get_escalation_config()
    assert isinstance(config, EscalationConfig)
    assert config.confidence_threshold == 0.85
    assert config.high_value_threshold == 5000.0
    assert config.oncology_flag is True
    assert config.incomplete_data_flag is True


def test_get_escalation_config_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """Environment overrides for escalation config."""
    monkeypatch.setenv("ESCALATION_CONFIDENCE_THRESHOLD", "0.72")
    monkeypatch.setenv("ESCALATION_HIGH_VALUE_THRESHOLD", "10000")
    monkeypatch.setenv("ESCALATION_ONCOLOGY_FLAG", "false")
    monkeypatch.setenv("ESCALATION_INCOMPLETE_DATA_FLAG", "false")
    # Re-read config (module may cache; get_escalation_config reads os.environ at call time)
    config = get_escalation_config()
    assert config.confidence_threshold == 0.72
    assert config.high_value_threshold == 10000.0
    assert config.oncology_flag is False
    assert config.incomplete_data_flag is False


def test_get_auth_required_procedures_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """get_auth_required_procedures returns default set when env unset."""
    monkeypatch.delenv("AUTH_REQUIRED_CPT_CODES", raising=False)
    procedures = get_auth_required_procedures()
    assert "73721" in procedures
    assert "70450" in procedures
    assert "72148" in procedures
    assert "29881" in procedures


def test_get_auth_required_procedures_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """get_auth_required_procedures parses comma-separated env var."""
    monkeypatch.setenv("AUTH_REQUIRED_CPT_CODES", "99213, 73721 , 27130")
    procedures = get_auth_required_procedures()
    assert procedures == {"99213", "73721", "27130"}


def test_get_payer_config_structure() -> None:
    """get_payer_config returns expected payer keys and structure."""
    config = get_payer_config()
    assert "UnitedHealthcare" in config
    assert "Aetna" in config
    assert "Cigna" in config
    for payer, rules in config.items():
        assert isinstance(rules, dict)
        assert "auth_required_cpt_override" in rules
        assert "common_denial_codes" in rules
