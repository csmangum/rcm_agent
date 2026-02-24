"""Tests for the custom exception hierarchy."""

import pytest

from rcm_agent.exceptions import (
    BackendError,
    DatabaseError,
    MigrationError,
    RcmAgentError,
    RoutingError,
    ValidationError,
)


def test_rcm_agent_error_base():
    err = RcmAgentError("something went wrong", encounter_id="ENC-001")
    assert str(err) == "something went wrong"
    assert err.encounter_id == "ENC-001"


def test_rcm_agent_error_default_encounter_id():
    err = RcmAgentError("oops")
    assert err.encounter_id is None


def test_backend_error_fields():
    err = BackendError(
        "timeout",
        encounter_id="ENC-002",
        backend="http://payer.example.com",
        status_code=504,
    )
    assert isinstance(err, RcmAgentError)
    assert err.backend == "http://payer.example.com"
    assert err.status_code == 504
    assert err.encounter_id == "ENC-002"


def test_routing_error_is_rcm_agent_error():
    err = RoutingError("no stage found", encounter_id="ENC-003")
    assert isinstance(err, RcmAgentError)


def test_validation_error_is_rcm_agent_error():
    err = ValidationError("bad data")
    assert isinstance(err, RcmAgentError)


def test_database_error_is_rcm_agent_error():
    err = DatabaseError("query failed")
    assert isinstance(err, RcmAgentError)


def test_migration_error_is_database_error():
    err = MigrationError("migration v2 failed")
    assert isinstance(err, DatabaseError)
    assert isinstance(err, RcmAgentError)


def test_exception_hierarchy_catch_base():
    """All custom exceptions should be catchable via RcmAgentError."""
    errors = [
        BackendError("b"),
        RoutingError("r"),
        ValidationError("v"),
        DatabaseError("d"),
        MigrationError("m"),
    ]
    for err in errors:
        with pytest.raises(RcmAgentError):
            raise err
