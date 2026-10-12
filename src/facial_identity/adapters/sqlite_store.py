"""Persistencia del prototipo en SQLite: sujetos, rostros registrados (solo referencia al motor
y hash de la imagen, nunca la imagen) y auditoría."""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime

from facial_identity.domain.models import (
    AuditAction,
    AuditEvent,
    Enrollment,
    Subject,
    SubjectStatus,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS subjects (
    id TEXT PRIMARY KEY,
    external_id TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    failed_attempts INTEGER NOT NULL DEFAULT 0,
    locked_until TEXT
);
CREATE TABLE IF NOT EXISTS enrollments (
    id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    engine_face_id TEXT NOT NULL,
    image_sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_events (
    id TEXT PRIMARY KEY,
    action TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    subject_id TEXT,
    outcome TEXT NOT NULL,
    detail TEXT NOT NULL,
    image_sha256 TEXT
);
CREATE INDEX IF NOT EXISTS ix_audit_subject ON audit_events(subject_id, occurred_at);
"""


class SqliteStore:
    """Implementa `SubjectRepository` y `AuditLog`. Usa ":memory:" en los tests."""

    def __init__(self, path: str) -> None:
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA foreign_keys = ON")
        self._db.executescript(_SCHEMA)

    def add(self, subject: Subject) -> None:
        self._execute(
            "INSERT INTO subjects VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                subject.id,
                subject.external_id,
                subject.display_name,
                subject.status.value,
                subject.created_at.isoformat(),
                subject.failed_attempts,
                _iso(subject.locked_until),
            ),
        )

    def update(self, subject: Subject) -> None:
        self._execute(
            "UPDATE subjects SET display_name = ?, status = ?, failed_attempts = ?,"
            " locked_until = ? WHERE id = ?",
            (
                subject.display_name,
                subject.status.value,
                subject.failed_attempts,
                _iso(subject.locked_until),
                subject.id,
            ),
        )

    def delete(self, subject_id: str) -> None:
        self._execute("DELETE FROM subjects WHERE id = ?", (subject_id,))

    def get(self, subject_id: str) -> Subject | None:
        rows = self._query("SELECT * FROM subjects WHERE id = ?", (subject_id,))
        return _to_subject(rows[0]) if rows else None

    def get_by_external_id(self, external_id: str) -> Subject | None:
        rows = self._query("SELECT * FROM subjects WHERE external_id = ?", (external_id,))
        return _to_subject(rows[0]) if rows else None

    def list_all(self) -> list[Subject]:
        return [_to_subject(r) for r in self._query("SELECT * FROM subjects ORDER BY created_at")]

    def add_enrollment(self, enrollment: Enrollment) -> None:
        self._execute(
            "INSERT INTO enrollments VALUES (?, ?, ?, ?, ?)",
            (
                enrollment.id,
                enrollment.subject_id,
                enrollment.engine_face_id,
                enrollment.image_sha256,
                enrollment.created_at.isoformat(),
            ),
        )

    def list_enrollments(self, subject_id: str) -> list[Enrollment]:
        rows = self._query(
            "SELECT * FROM enrollments WHERE subject_id = ? ORDER BY created_at", (subject_id,)
        )
        return [
            Enrollment(
                id=r["id"],
                subject_id=r["subject_id"],
                engine_face_id=r["engine_face_id"],
                image_sha256=r["image_sha256"],
                created_at=datetime.fromisoformat(r["created_at"]),
            )
            for r in rows
        ]

    def record(self, event: AuditEvent) -> None:
        self._execute(
            "INSERT INTO audit_events VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                event.id,
                event.action.value,
                event.occurred_at.isoformat(),
                event.subject_id,
                event.outcome,
                event.detail,
                event.image_sha256,
            ),
        )

    def list_events(self, subject_id: str | None = None, limit: int = 100) -> list[AuditEvent]:
        sql = "SELECT * FROM audit_events"
        params: tuple[object, ...] = ()
        if subject_id:
            sql += " WHERE subject_id = ?"
            params = (subject_id,)
        rows = self._query(f"{sql} ORDER BY occurred_at DESC, rowid DESC LIMIT ?", (*params, limit))
        return [
            AuditEvent(
                id=r["id"],
                action=AuditAction(r["action"]),
                occurred_at=datetime.fromisoformat(r["occurred_at"]),
                subject_id=r["subject_id"],
                outcome=r["outcome"],
                detail=r["detail"],
                image_sha256=r["image_sha256"],
            )
            for r in rows
        ]

    def _execute(self, sql: str, params: tuple[object, ...]) -> None:
        with self._lock, self._db:
            self._db.execute(sql, params)

    def _query(self, sql: str, params: tuple[object, ...] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._db.execute(sql, params).fetchall()


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _to_subject(row: sqlite3.Row) -> Subject:
    return Subject(
        id=row["id"],
        external_id=row["external_id"],
        display_name=row["display_name"],
        status=SubjectStatus(row["status"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        failed_attempts=row["failed_attempts"],
        locked_until=datetime.fromisoformat(row["locked_until"]) if row["locked_until"] else None,
    )
