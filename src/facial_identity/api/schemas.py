"""Contrato público normalizado. Nada de aquí refleja la forma de las respuestas de CompreFace."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from facial_identity.domain.models import (
    AuditEvent,
    Candidate,
    Decision,
    Enrollment,
    IdentificationResult,
    ReasonCode,
    Subject,
    SubjectStatus,
    VerificationResult,
)


class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class SubjectCreate(ApiModel):
    external_id: str = Field(min_length=1, max_length=64, examples=["CUST-1001"])
    display_name: str = Field(min_length=1, max_length=120, examples=["Ana Pérez"])


class SubjectOut(ApiModel):
    subject_id: str
    external_id: str
    display_name: str
    status: SubjectStatus
    enrollments: int
    failed_attempts: int
    locked_until: datetime | None
    created_at: datetime

    @classmethod
    def of(cls, subject: Subject, enrollments: int) -> SubjectOut:
        return cls(
            subject_id=subject.id,
            external_id=subject.external_id,
            display_name=subject.display_name,
            status=subject.status,
            enrollments=enrollments,
            failed_attempts=subject.failed_attempts,
            locked_until=subject.locked_until,
            created_at=subject.created_at,
        )


class EnrollmentOut(ApiModel):
    enrollment_id: str
    subject_id: str
    created_at: datetime

    @classmethod
    def of(cls, enrollment: Enrollment) -> EnrollmentOut:
        return cls(
            enrollment_id=enrollment.id,
            subject_id=enrollment.subject_id,
            created_at=enrollment.created_at,
        )


class VerificationOut(ApiModel):
    verification_id: str
    subject_id: str
    decision: Decision
    score: float
    reason_code: ReasonCode

    @classmethod
    def of(cls, result: VerificationResult) -> VerificationOut:
        return cls(
            verification_id=result.id,
            subject_id=result.subject_id,
            decision=result.decision,
            score=result.score,
            reason_code=result.reason_code,
        )


class CandidateOut(ApiModel):
    subject_id: str
    external_id: str
    display_name: str
    score: float

    @classmethod
    def of(cls, candidate: Candidate) -> CandidateOut:
        return cls(
            subject_id=candidate.subject_id,
            external_id=candidate.external_id,
            display_name=candidate.display_name,
            score=candidate.score,
        )


class IdentificationOut(ApiModel):
    identification_id: str
    decision: Decision
    reason_code: ReasonCode
    candidates: list[CandidateOut]

    @classmethod
    def of(cls, result: IdentificationResult) -> IdentificationOut:
        return cls(
            identification_id=result.id,
            decision=result.decision,
            reason_code=result.reason_code,
            candidates=[CandidateOut.of(c) for c in result.candidates],
        )


class AuditEventOut(ApiModel):
    event_id: str
    action: str
    occurred_at: datetime
    subject_id: str | None
    outcome: str
    detail: str
    image_sha256: str | None

    @classmethod
    def of(cls, event: AuditEvent) -> AuditEventOut:
        return cls(
            event_id=event.id,
            action=event.action.value,
            occurred_at=event.occurred_at,
            subject_id=event.subject_id,
            outcome=event.outcome,
            detail=event.detail,
            image_sha256=event.image_sha256,
        )


class HealthOut(ApiModel):
    status: str
    engine: str
    engine_status: str
