"""Repository for encounter persistence and audit."""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from rcm_agent.db.schema import init_db
from rcm_agent.models import (
    ClaimSubmission,
    Encounter,
    EncounterStatus,
    PriorAuthRequest,
    RcmStage,
)


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _row_to_encounter_dict(row: tuple) -> dict:
    """Convert encounters table row to dict with nested structures."""
    (
        encounter_id,
        patient,
        insurance,
        date,
        type_,
        procedures,
        diagnoses,
        clinical_notes,
        documents,
        stage,
        status,
        created_at,
        updated_at,
    ) = row
    return {
        "encounter_id": encounter_id,
        "patient": json.loads(patient),
        "insurance": json.loads(insurance),
        "date": date,
        "type": type_,
        "procedures": json.loads(procedures),
        "diagnoses": json.loads(diagnoses),
        "clinical_notes": clinical_notes,
        "documents": json.loads(documents),
        "stage": stage,
        "status": status,
        "created_at": created_at,
        "updated_at": updated_at,
    }


class EncounterRepository:
    """SQLite-backed repository for encounters and audit trail."""

    def __init__(self, db_path: str) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        init_db(db_path)
        self._db_path = db_path

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def save_encounter(
        self,
        encounter: Encounter,
        stage: RcmStage,
        status: EncounterStatus,
    ) -> None:
        """Insert or replace encounter row."""
        now = _now_utc()
        conn = self._conn()
        try:
            conn.execute(
                """
                INSERT INTO encounters (
                    encounter_id, patient, insurance, date, type,
                    procedures, diagnoses, clinical_notes, documents,
                    stage, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(encounter_id) DO UPDATE SET
                    patient = excluded.patient,
                    insurance = excluded.insurance,
                    date = excluded.date,
                    type = excluded.type,
                    procedures = excluded.procedures,
                    diagnoses = excluded.diagnoses,
                    clinical_notes = excluded.clinical_notes,
                    documents = excluded.documents,
                    stage = excluded.stage,
                    status = excluded.status,
                    updated_at = excluded.updated_at
                """,
                (
                    encounter.encounter_id,
                    encounter.patient.model_dump_json(),
                    encounter.insurance.model_dump_json(),
                    encounter.date,
                    encounter.type.value,
                    json.dumps([p.model_dump() for p in encounter.procedures]),
                    json.dumps([d.model_dump() for d in encounter.diagnoses]),
                    encounter.clinical_notes,
                    json.dumps(encounter.documents),
                    stage.value,
                    status.value,
                    now,
                    now,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def get_encounter(self, encounter_id: str) -> dict | None:
        """Return encounter row as dict with parsed JSON fields, or None."""
        conn = self._conn()
        try:
            cur = conn.execute(
                """
                SELECT encounter_id, patient, insurance, date, type,
                       procedures, diagnoses, clinical_notes, documents,
                       stage, status, created_at, updated_at
                FROM encounters WHERE encounter_id = ?
                """,
                (encounter_id,),
            )
            row = cur.fetchone()
            return _row_to_encounter_dict(row) if row else None
        finally:
            conn.close()

    def update_status(
        self,
        encounter_id: str,
        new_status: EncounterStatus,
        action_description: str,
        *,
        new_stage: RcmStage | None = None,
        old_status: str | None = None,
        details: str | None = None,
    ) -> None:
        """Update encounter status and append audit log row (transactional)."""
        conn = self._conn()
        try:
            cur = conn.execute(
                "SELECT status, stage FROM encounters WHERE encounter_id = ?",
                (encounter_id,),
            )
            row = cur.fetchone()
            if not row:
                return
            current_status, _current_stage = row

            updates = ["status = ?", "updated_at = ?"]
            params: list = [new_status.value, _now_utc()]
            if new_stage is not None:
                updates.append("stage = ?")
                params.append(new_stage.value)
            params.append(encounter_id)

            conn.execute(
                f"UPDATE encounters SET {', '.join(updates)} WHERE encounter_id = ?",
                params,
            )
            conn.execute(
                """
                INSERT INTO encounter_audit_log
                (encounter_id, action, old_status, new_status, details, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    encounter_id,
                    action_description,
                    old_status or current_status,
                    new_status.value,
                    details,
                    _now_utc(),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def get_audit_log(self, encounter_id: str) -> list[dict]:
        """Return audit log entries for encounter, oldest first."""
        conn = self._conn()
        try:
            cur = conn.execute(
                """
                SELECT id, encounter_id, action, old_status, new_status, details, created_at
                FROM encounter_audit_log
                WHERE encounter_id = ?
                ORDER BY id ASC
                """,
                (encounter_id,),
            )
            rows = cur.fetchall()
            return [
                {
                    "id": r[0],
                    "encounter_id": r[1],
                    "action": r[2],
                    "old_status": r[3],
                    "new_status": r[4],
                    "details": r[5],
                    "created_at": r[6],
                }
                for r in rows
            ]
        finally:
            conn.close()

    def save_workflow_run(
        self,
        encounter_id: str,
        stage: RcmStage,
        router_output: dict,
        workflow_output: dict,
    ) -> None:
        """Insert a workflow run record."""
        conn = self._conn()
        try:
            conn.execute(
                """
                INSERT INTO workflow_runs
                (encounter_id, stage, router_output, workflow_output, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    encounter_id,
                    stage.value,
                    json.dumps(router_output),
                    json.dumps(workflow_output),
                    _now_utc(),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def save_prior_auth(self, prior_auth_request: PriorAuthRequest) -> None:
        """Insert or replace prior auth request."""
        conn = self._conn()
        try:
            conn.execute(
                """
                INSERT INTO prior_auth_requests (
                    auth_id, encounter_id, payer, procedure_codes,
                    clinical_justification, status, submitted_at,
                    decision, decision_date
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(auth_id) DO UPDATE SET
                    encounter_id = excluded.encounter_id,
                    payer = excluded.payer,
                    procedure_codes = excluded.procedure_codes,
                    clinical_justification = excluded.clinical_justification,
                    status = excluded.status,
                    submitted_at = excluded.submitted_at,
                    decision = excluded.decision,
                    decision_date = excluded.decision_date
                """,
                (
                    prior_auth_request.auth_id,
                    prior_auth_request.encounter_id,
                    prior_auth_request.payer,
                    json.dumps(prior_auth_request.procedure_codes),
                    prior_auth_request.clinical_justification,
                    prior_auth_request.status.value,
                    prior_auth_request.submitted_at,
                    prior_auth_request.decision.value if prior_auth_request.decision is not None else None,
                    prior_auth_request.decision_date,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def save_claim_submission(self, claim_submission: ClaimSubmission) -> None:
        """Insert or replace claim submission."""
        conn = self._conn()
        try:
            conn.execute(
                """
                INSERT INTO claim_submissions (
                    claim_id, encounter_id, payer, total_charges,
                    icd_codes, cpt_codes, modifiers, status, submitted_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(claim_id) DO UPDATE SET
                    encounter_id = excluded.encounter_id,
                    payer = excluded.payer,
                    total_charges = excluded.total_charges,
                    icd_codes = excluded.icd_codes,
                    cpt_codes = excluded.cpt_codes,
                    modifiers = excluded.modifiers,
                    status = excluded.status,
                    submitted_at = excluded.submitted_at
                """,
                (
                    claim_submission.claim_id,
                    claim_submission.encounter_id,
                    claim_submission.payer,
                    claim_submission.total_charges,
                    json.dumps(claim_submission.icd_codes),
                    json.dumps(claim_submission.cpt_codes),
                    json.dumps(claim_submission.modifiers),
                    claim_submission.status.value,
                    claim_submission.submitted_at,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def save_denial_event(
        self,
        encounter_id: str,
        reason_codes: list[str],
        denial_type: str,
        appeal_viable: bool,
        *,
        claim_id: str | None = None,
        payer: str | None = None,
    ) -> None:
        """Insert a denial event for analytics. Call only after the encounter has been saved; denial_events.encounter_id references encounters(encounter_id)."""
        conn = self._conn()
        try:
            conn.execute(
                """
                INSERT INTO denial_events
                (encounter_id, claim_id, payer, reason_codes, denial_type, appeal_viable, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    encounter_id,
                    claim_id,
                    payer,
                    json.dumps(reason_codes),
                    denial_type,
                    1 if appeal_viable else 0,
                    _now_utc(),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def get_denial_events(self, encounter_id: str) -> list[dict]:
        """Return denial events for an encounter, newest first."""
        conn = self._conn()
        try:
            cur = conn.execute(
                """
                SELECT id, encounter_id, claim_id, payer, reason_codes, denial_type, appeal_viable, created_at
                FROM denial_events
                WHERE encounter_id = ?
                ORDER BY id DESC
                """,
                (encounter_id,),
            )
            rows = cur.fetchall()
            return [
                {
                    "id": r[0],
                    "encounter_id": r[1],
                    "claim_id": r[2],
                    "payer": r[3],
                    "reason_codes": json.loads(r[4]) if r[4] else [],
                    "denial_type": r[5],
                    "appeal_viable": bool(r[6]),
                    "created_at": r[7],
                }
                for r in rows
            ]
        finally:
            conn.close()

    def get_denial_stats(self) -> dict:
        """Aggregate denial analytics: by reason code, denial type, payer."""
        conn = self._conn()
        try:
            cur = conn.execute("SELECT reason_codes, denial_type, payer FROM denial_events")
            rows = cur.fetchall()

            by_reason_code: dict[str, int] = {}
            by_denial_type: dict[str, int] = {}
            by_payer: dict[str, int] = {}
            total = 0
            appeal_viable_count = 0

            cur2 = conn.execute("SELECT COUNT(*), SUM(appeal_viable) FROM denial_events")
            row2 = cur2.fetchone()
            if row2:
                total = row2[0] or 0
                appeal_viable_count = row2[1] or 0

            for reason_codes_json, denial_type, payer in rows:
                if denial_type:
                    by_denial_type[denial_type] = by_denial_type.get(denial_type, 0) + 1
                if payer:
                    by_payer[payer] = by_payer.get(payer, 0) + 1
                try:
                    codes = json.loads(reason_codes_json) if reason_codes_json else []
                    for c in codes:
                        by_reason_code[c] = by_reason_code.get(c, 0) + 1
                except (json.JSONDecodeError, TypeError):
                    pass

            return {
                "total": total,
                "appeal_viable_count": appeal_viable_count,
                "by_reason_code": by_reason_code,
                "by_denial_type": by_denial_type,
                "by_payer": by_payer,
            }
        finally:
            conn.close()

    def get_metrics(self) -> dict:
        """Aggregate counts by status and stage for metrics command."""
        conn = self._conn()
        try:
            cur = conn.execute("SELECT status, COUNT(*) FROM encounters GROUP BY status")
            by_status = dict(cur.fetchall())

            cur = conn.execute("SELECT stage, COUNT(*) FROM encounters GROUP BY stage")
            by_stage = dict(cur.fetchall())

            cur = conn.execute("SELECT COUNT(*) FROM encounters")
            total = cur.fetchone()[0]

            escalated = by_status.get(EncounterStatus.ESCALATED.value, 0) + by_status.get(
                EncounterStatus.NEEDS_REVIEW.value, 0
            )
            clean = (
                by_status.get(EncounterStatus.CLAIM_ACCEPTED.value, 0)
                + by_status.get(EncounterStatus.CODED.value, 0)
                + by_status.get(EncounterStatus.ELIGIBLE.value, 0)
                + by_status.get(EncounterStatus.AUTH_APPROVED.value, 0)
            )

            denial_stats = self.get_denial_stats()

            return {
                "total": total,
                "by_status": by_status,
                "by_stage": by_stage,
                "escalated_count": escalated,
                "escalation_pct": (escalated / total * 100) if total else 0.0,
                "clean_count": clean,
                "clean_rate_pct": (clean / total * 100) if total else 0.0,
                "denial_stats": denial_stats,
            }
        finally:
            conn.close()
