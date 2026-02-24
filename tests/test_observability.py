"""Tests for the observability / structured logging module."""

import json
import logging
from io import StringIO

from rcm_agent.observability.logging import (
    StructuredLogger,
    _HumanFormatter,
    _JsonFormatter,
    get_logger,
    reset_logging,
    setup_logging,
)


def _capture_log_output(logger_name: str, fmt: str = "json") -> tuple[StructuredLogger, StringIO]:
    """Create a logger with a StringIO handler for testing."""
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    if fmt == "json":
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(_HumanFormatter())
    lgr = get_logger(logger_name)
    lgr.handlers.clear()
    lgr.addHandler(handler)
    lgr.setLevel(logging.DEBUG)
    lgr.propagate = False
    return lgr, stream


def test_json_formatter_basic_message():
    lgr, stream = _capture_log_output("test.json.basic")
    lgr.info("hello world")
    output = stream.getvalue().strip()
    parsed = json.loads(output)
    assert parsed["message"] == "hello world"
    assert parsed["level"] == "INFO"
    assert "ts" in parsed


def test_json_formatter_extra_fields():
    lgr, stream = _capture_log_output("test.json.extra")
    lgr.info("Router classified", encounter_id="ENC-001", stage="CODING", confidence=0.95)
    output = stream.getvalue().strip()
    parsed = json.loads(output)
    assert parsed["encounter_id"] == "ENC-001"
    assert parsed["stage"] == "CODING"
    assert parsed["confidence"] == 0.95


def test_human_formatter_basic_message():
    lgr, stream = _capture_log_output("test.human.basic", fmt="human")
    lgr.info("hello world")
    output = stream.getvalue().strip()
    assert "hello world" in output
    assert "INFO" in output


def test_human_formatter_extra_fields():
    lgr, stream = _capture_log_output("test.human.extra", fmt="human")
    lgr.info("Router classified", encounter_id="ENC-001", stage="CODING")
    output = stream.getvalue().strip()
    assert "encounter_id=ENC-001" in output
    assert "stage=CODING" in output


def test_json_formatter_exception():
    lgr, stream = _capture_log_output("test.json.exc")
    try:
        raise ValueError("test error")
    except ValueError:
        lgr.exception("something failed")
    output = stream.getvalue().strip()
    parsed = json.loads(output)
    assert "exception" in parsed
    assert "ValueError" in parsed["exception"]


def test_get_logger_returns_structured_logger():
    lgr = get_logger("test.structured")
    assert isinstance(lgr, StructuredLogger)


def test_setup_logging_idempotent():
    reset_logging()
    setup_logging(level="DEBUG", fmt="json")
    root_handlers = len(logging.getLogger().handlers)
    setup_logging(level="DEBUG", fmt="json")
    assert len(logging.getLogger().handlers) == root_handlers
    reset_logging()


def test_setup_logging_human_format():
    reset_logging()
    setup_logging(level="INFO", fmt="human")
    root = logging.getLogger()
    assert len(root.handlers) == 1
    assert isinstance(root.handlers[0].formatter, _HumanFormatter)
    reset_logging()


def test_setup_logging_json_format():
    reset_logging()
    setup_logging(level="INFO", fmt="json")
    root = logging.getLogger()
    assert len(root.handlers) == 1
    assert isinstance(root.handlers[0].formatter, _JsonFormatter)
    reset_logging()
