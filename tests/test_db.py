"""Unit tests for database schema and repository."""

import json
from pathlib import Path

import pytest

from rcm_agent.db import EncounterRepository, init_db
from rcm_agent.models import (
    ClaimSubmission,
    Encounter,
    EncounterStatus,
    PriorAuthRequest,
    RcmStage,
)


@pytest.fixture
def sample_encounter() -> Encounter:
    """Minimal encounter for DB tests."""
    return Encounter(
        encounter_id="ENC-DB-001",
        patient={"age": 30, "gender": "F", "zip": "10001"},
        insurance={"payer": "Aetna", "member_id": "M1", "plan_type": "PPO"},
        date="2026-02-10",
        type="office_visit",
        procedures=[{"code": "99213", "description": "Office visit"}],
        diagnoses=[{"code": "J06.9", "description": "URI"}],
        clinical_notes="Test.",
        documents=[],
    )


def test_init_db_creates_tables(tmp_path: Path) -> None:
    """init_db creates all tables."""
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    import sqlite3
    conn = sqlite3.connect(db_path)
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = [row[0] for row in cur.fetchall()]
    conn.close()
    assert "encounters" in tables
    assert "encounter_audit_log" in tables
    assert "workflow_runs" in tables
    assert "prior_auth_requests" in tables
    assert "claim_submissions" in tables
    assert "denial_events" in tables


def test_save_and_get_encounter_round_trip(tmp_path: Path, sample_encounter: Encounter) -> None:
    """save_encounter then get_encounter returns same data."""
    db_path = str(tmp_path / "test.db")
    repo = EncounterRepository(db_path)
    repo.save_encounter(sample_encounter, RcmStage.CODING_CHARGE_CAPTURE, EncounterStatus.PENDING)
    row = repo.get_encounter("ENC-DB-001")
    assert row is not None
    assert row["encounter_id"] == "ENC-DB-001"
    assert row["stage"] == RcmStage.CODING_CHARGE_CAPTURE.value
    assert row["status"] == EncounterStatus.PENDING.value
    assert row["patient"]["age"] == 30
    assert row["insurance"]["payer"] == "Aetna"
    assert len(row["procedures"]) == 1
    assert row["procedures"][0]["code"] == "99213"


def test_get_encounter_missing_returns_none(tmp_path: Path) -> None:
    """get_encounter for unknown id returns None."""
    db_path = str(tmp_path / "test.db")
    repo = EncounterRepository(db_path)
    assert repo.get_encounter("NONEXISTENT") is None


def test_update_status_writes_audit_log(tmp_path: Path, sample_encounter: Encounter) -> None:
    """update_status updates encounter and appends audit log."""
    db_path = str(tmp_path / "test.db")
    repo = EncounterRepository(db_path)
    repo.save_encounter(sample_encounter, RcmStage.CODING_CHARGE_CAPTURE, EncounterStatus.PENDING)
    repo.update_status(
        "ENC-DB-001",
        EncounterStatus.CODED,
        "stub_complete",
        details="Mock coding done",
    )
    log = repo.get_audit_log("ENC-DB-001")
    assert len(log) == 1
    assert log[0]["action"] == "stub_complete"
    assert log[0]["old_status"] == EncounterStatus.PENDING.value
    assert log[0]["new_status"] == EncounterStatus.CODED.value
    row = repo.get_encounter("ENC-DB-001")
    assert row["status"] == EncounterStatus.CODED.value


def test_get_audit_log_ordered_by_id(tmp_path: Path, sample_encounter: Encounter) -> None:
    """get_audit_log returns entries oldest first."""
    db_path = str(tmp_path / "test.db")
    repo = EncounterRepository(db_path)
    repo.save_encounter(sample_encounter, RcmStage.CODING_CHARGE_CAPTURE, EncounterStatus.PENDING)
    repo.update_status("ENC-DB-001", EncounterStatus.PROCESSING, "step1")
    repo.update_status("ENC-DB-001", EncounterStatus.CODED, "step2")
    log = repo.get_audit_log("ENC-DB-001")
    assert len(log) == 2
    assert log[0]["action"] == "step1"
    assert log[1]["action"] == "step2"


def test_save_workflow_run(tmp_path: Path, sample_encounter: Encounter) -> None:
    """save_workflow_run persists a run."""
    db_path = str(tmp_path / "test.db")
    repo = EncounterRepository(db_path)
    repo.save_encounter(sample_encounter, RcmStage.CODING_CHARGE_CAPTURE, EncounterStatus.PENDING)
    repo.save_workflow_run(
        "ENC-DB-001",
        RcmStage.CODING_CHARGE_CAPTURE,
        {"router": "stub"},
        {"output": "coded"},
    )
    # No getter in repo; just ensure no exception and table has row
    import sqlite3
    conn = sqlite3.connect(db_path)
    cur = conn.execute("SELECT COUNT(*) FROM workflow_runs WHERE encounter_id = ?", ("ENC-DB-001",))
    assert cur.fetchone()[0] == 1
    conn.close()


def test_save_prior_auth(tmp_path: Path, sample_encounter: Encounter) -> None:
    """save_prior_auth persists prior auth request."""
    from rcm_agent.models import PriorAuthDecision, PriorAuthStatus

    db_path = str(tmp_path / "test.db")
    repo = EncounterRepository(db_path)
    repo.save_encounter(sample_encounter, RcmStage.PRIOR_AUTHORIZATION, EncounterStatus.PENDING)
    auth = PriorAuthRequest(
        auth_id="AUTH-1",
        encounter_id="ENC-DB-001",
        payer="Aetna",
        procedure_codes=["73721"],
        clinical_justification="Knee pain.",
        status=PriorAuthStatus.APPROVED,
        submitted_at="2026-02-10T12:00:00Z",
        decision=PriorAuthDecision.APPROVED,
        decision_date="2026-02-12",
    )
    repo.save_prior_auth(auth)
    import sqlite3
    conn = sqlite3.connect(db_path)
    cur = conn.execute("SELECT auth_id, status FROM prior_auth_requests WHERE auth_id = ?", ("AUTH-1",))
    row = cur.fetchone()
    assert row is not None
    assert row[1] == "approved"
    conn.close()


def test_save_claim_submission(tmp_path: Path, sample_encounter: Encounter) -> None:
    """save_claim_submission persists claim."""
    from rcm_agent.models import ClaimStatus

    db_path = str(tmp_path / "test.db")
    repo = EncounterRepository(db_path)
    repo.save_encounter(sample_encounter, RcmStage.CLAIMS_SUBMISSION, EncounterStatus.PENDING)
    claim = ClaimSubmission(
        claim_id="CLM-1",
        encounter_id="ENC-DB-001",
        payer="Aetna",
        total_charges=100.0,
        icd_codes=["J06.9"],
        cpt_codes=["99213"],
        modifiers=[],
        status=ClaimStatus.SUBMITTED,
        submitted_at="2026-02-11T00:00:00Z",
    )
    repo.save_claim_submission(claim)
    import sqlite3
    conn = sqlite3.connect(db_path)
    cur = conn.execute("SELECT claim_id, total_charges FROM claim_submissions WHERE claim_id = ?", ("CLM-1",))
    row = cur.fetchone()
    assert row is not None
    assert row[1] == 100.0
    conn.close()


def test_update_status_nonexistent_encounter_id(tmp_path: Path) -> None:
    """update_status with non-existent encounter_id does nothing and does not raise."""
    db_path = str(tmp_path / "test.db")
    repo = EncounterRepository(db_path)
    repo.update_status("NONEXISTENT", EncounterStatus.CODED, "noop")


def test_save_denial_event(tmp_path: Path, sample_encounter: Encounter) -> None:
    """save_denial_event persists a denial event."""
    db_path = str(tmp_path / "test.db")
    repo = EncounterRepository(db_path)
    repo.save_encounter(sample_encounter, RcmStage.DENIAL_APPEAL, EncounterStatus.CLAIM_DENIED)
    repo.save_denial_event(
        encounter_id="ENC-DB-001",
        reason_codes=["CO-4", "PR-96"],
        denial_type="administrative",
        appeal_viable=True,
        claim_id="CLM-1",
        payer="Aetna",
    )
    events = repo.get_denial_events("ENC-DB-001")
    assert len(events) == 1
    assert events[0]["reason_codes"] == ["CO-4", "PR-96"]
    assert events[0]["denial_type"] == "administrative"
    assert events[0]["appeal_viable"] is True
    assert events[0]["claim_id"] == "CLM-1"
    assert events[0]["payer"] == "Aetna"


def test_get_denial_events_empty(tmp_path: Path) -> None:
    """get_denial_events for encounter with no events returns empty list."""
    db_path = str(tmp_path / "test.db")
    repo = EncounterRepository(db_path)
    assert repo.get_denial_events("ENC-NONE") == []


def test_get_denial_stats(tmp_path: Path, sample_encounter: Encounter) -> None:
    """get_denial_stats returns by_reason_code, by_denial_type, by_payer."""
    db_path = str(tmp_path / "test.db")
    repo = EncounterRepository(db_path)
    repo.save_encounter(sample_encounter, RcmStage.DENIAL_APPEAL, EncounterStatus.CLAIM_DENIED)
    repo.save_denial_event("ENC-DB-001", ["CO-4", "PR-96"], "administrative", True, payer="Aetna")
    repo.save_denial_event("ENC-DB-001", ["CO-4"], "clinical", False, payer="Aetna")
    stats = repo.get_denial_stats()
    assert stats["total"] == 2
    assert stats["appeal_viable_count"] == 1
    assert stats["by_reason_code"]["CO-4"] == 2
    assert stats["by_reason_code"]["PR-96"] == 1
    assert stats["by_denial_type"]["administrative"] == 1
    assert stats["by_denial_type"]["clinical"] == 1
    assert stats["by_payer"]["Aetna"] == 2


def test_get_metrics(tmp_path: Path, sample_encounter: Encounter) -> None:
    """get_metrics returns aggregate counts."""
    db_path = str(tmp_path / "test.db")
    repo = EncounterRepository(db_path)
    repo.save_encounter(sample_encounter, RcmStage.CODING_CHARGE_CAPTURE, EncounterStatus.CODED)
    e2 = Encounter(
        encounter_id="ENC-DB-002",
        patient={"age": 50, "gender": "M", "zip": "90210"},
        insurance={"payer": "UHC", "member_id": "M2", "plan_type": "PPO"},
        date="2026-02-11",
        type="outpatient_procedure",
        procedures=[{"code": "73721", "description": "MRI"}],
        diagnoses=[{"code": "M25.561", "description": "Knee pain"}],
        clinical_notes="Notes",
        documents=[],
    )
    repo.save_encounter(e2, RcmStage.PRIOR_AUTHORIZATION, EncounterStatus.NEEDS_REVIEW)
    m = repo.get_metrics()
    assert m["total"] == 2
    assert m["by_status"][EncounterStatus.CODED.value] == 1
    assert m["by_status"][EncounterStatus.NEEDS_REVIEW.value] == 1
    assert m["clean_count"] == 1
    assert m["escalated_count"] == 1
    assert m["clean_rate_pct"] == 50.0
    assert m["escalation_pct"] == 50.0
    assert "denial_stats" in m
    assert m["denial_stats"]["total"] == 0
