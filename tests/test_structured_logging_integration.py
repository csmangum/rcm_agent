"""Integration tests verifying structured logging at key decision points."""

import json
import logging
from io import StringIO

import pytest

from rcm_agent.models import Encounter
from rcm_agent.observability.logging import _JsonFormatter, get_logger


@pytest.fixture
def capture_json_logs():
    """Capture JSON-formatted log records into a list of parsed dicts."""
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(_JsonFormatter())

    loggers = [
        get_logger("rcm_agent.crews.router"),
        get_logger("rcm_agent.crews.main_crew"),
        get_logger("rcm_agent.tools.logic"),
        get_logger("rcm_agent.db.repository"),
    ]
    original_handlers = {}
    for lgr in loggers:
        original_handlers[lgr.name] = lgr.handlers[:]
        lgr.handlers.clear()
        lgr.addHandler(handler)
        lgr.setLevel(logging.DEBUG)
        lgr.propagate = False

    def get_records() -> list[dict]:
        stream.seek(0)
        lines = stream.getvalue().strip().split("\n")
        return [json.loads(line) for line in lines if line.strip()]

    yield get_records

    for lgr in loggers:
        lgr.handlers.clear()
        for h in original_handlers[lgr.name]:
            lgr.addHandler(h)


def test_router_classification_emits_encounter_id(capture_json_logs, encounter_001: Encounter):
    from rcm_agent.crews.router import classify_encounter

    classify_encounter(encounter_001)
    records = capture_json_logs()
    router_records = [r for r in records if r.get("action") == "heuristic_classify"]
    assert len(router_records) >= 1
    rec = router_records[0]
    assert rec["encounter_id"] == encounter_001.encounter_id
    assert "stage" in rec
    assert "confidence" in rec


def test_escalation_check_emits_structured_log(capture_json_logs, encounter_001: Encounter):
    from rcm_agent.tools.logic import check_escalation

    check_escalation(encounter_001, confidence=0.99, estimated_charges=100.0)
    records = capture_json_logs()
    esc_records = [r for r in records if r.get("action") == "escalation_check"]
    assert len(esc_records) >= 1
    assert esc_records[0]["encounter_id"] == encounter_001.encounter_id
