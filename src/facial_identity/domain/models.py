from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum


class SubjectStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class Decision(StrEnum):
    MATCH = "MATCH"
    NO_MATCH = "NO_MATCH"
    INCONCLUSIVE = "INCONCLUSIVE"


class ReasonCode(StrEnum):
    SCORE_ABOVE_THRESHOLD = "SCORE_ABOVE_THRESHOLD"
    SCORE_IN_GRAY_ZONE = "SCORE_IN_GRAY_ZONE"
    SCORE_BELOW_THRESHOLD = "SCORE_BELOW_THRESHOLD"
    NO_CANDIDATES = "NO_CANDIDATES"


class LivenessResult(StrEnum):
    """Resultado de la prueba de vida que hizo el consumidor (p. ej. parpadeo y giro de cabeza
    en el dispositivo). El servicio solo lo registra en la auditoría."""

    PASSED = "PASSED"
    FAILED = "FAILED"
    NOT_PERFORMED = "NOT_PERFORMED"


class AuditAction(StrEnum):
    SUBJECT_CREATED = "SUBJECT_CREATED"
    CONSENT_GRANTED = "CONSENT_GRANTED"
    FACE_ENROLLED = "FACE_ENROLLED"
    FACE_VERIFIED = "FACE_VERIFIED"
    FACE_IDENTIFIED = "FACE_IDENTIFIED"
    SUBJECT_DEACTIVATED = "SUBJECT_DEACTIVATED"
    SUBJECT_REACTIVATED = "SUBJECT_REACTIVATED"
    SUBJECT_DELETED = "SUBJECT_DELETED"


@dataclass(frozen=True)
class Subject:
    """Persona registrada. `id` es el identificador opaco que ve el motor; `external_id` es el
    identificador de negocio del consumidor (p. ej. customerId) y nunca sale hacia el motor."""

    id: str
    external_id: str
    display_name: str
    status: SubjectStatus
    created_at: datetime
    failed_attempts: int = 0
    locked_until: datetime | None = None

    @property
    def is_active(self) -> bool:
        return self.status is SubjectStatus.ACTIVE

    def is_locked(self, now: datetime) -> bool:
        return self.locked_until is not None and now < self.locked_until

    def with_status(self, status: SubjectStatus) -> Subject:
        return replace(self, status=status)

    def with_failed_attempt(self, locked_until: datetime | None) -> Subject:
        return replace(self, failed_attempts=self.failed_attempts + 1, locked_until=locked_until)

    def with_attempts_reset(self) -> Subject:
        return replace(self, failed_attempts=0, locked_until=None)


@dataclass(frozen=True)
class Consent:
    """Autorización expresa de la persona para tratar sus datos biométricos (Ley 1581 de 2012)."""

    id: str
    subject_id: str
    text_version: str
    channel: str
    granted_at: datetime


@dataclass(frozen=True)
class SubjectSummary:
    subject: Subject
    enrollments: int
    consented_at: datetime | None


@dataclass(frozen=True)
class Enrollment:
    id: str
    subject_id: str
    engine_face_id: str
    image_sha256: str
    created_at: datetime


@dataclass(frozen=True)
class EngineMatch:
    """Coincidencia cruda devuelta por un motor: sujeto del motor + similitud 0..1."""

    engine_subject: str
    similarity: float


@dataclass(frozen=True)
class VerificationResult:
    id: str
    subject_id: str
    decision: Decision
    score: float
    reason_code: ReasonCode


@dataclass(frozen=True)
class Candidate:
    subject_id: str
    external_id: str
    display_name: str
    score: float


@dataclass(frozen=True)
class IdentificationResult:
    id: str
    decision: Decision
    reason_code: ReasonCode
    candidates: list[Candidate]


@dataclass(frozen=True)
class AuditEvent:
    id: str
    action: AuditAction
    occurred_at: datetime
    subject_id: str | None = None
    outcome: str = "OK"
    detail: str = ""
    image_sha256: str | None = None
