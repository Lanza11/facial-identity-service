"""Contrato público normalizado. Nada de aquí refleja la forma de las respuestas de CompreFace.
Las descripciones y ejemplos de los campos son los que muestra Swagger (/docs)."""

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

_EXAMPLE_NAME = "Ana Pérez"
_EXAMPLE_EXTERNAL_ID = "CUST-1001"
_SUBJECT_ID = "1c0e6a52-7b8f-4f4e-9a51-2f7f0c9d3b11"
_SCORE = "Similitud entre 0 y 1 calculada por el motor (1 = mismo rostro)."


class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class SubjectCreate(ApiModel):
    external_id: str = Field(
        min_length=1,
        max_length=64,
        description="Identificador de la persona en el sistema consumidor (p. ej. el `customerId` "
        "de la app). Único. Nunca se envía al motor.",
        examples=[_EXAMPLE_EXTERNAL_ID],
    )
    display_name: str = Field(
        min_length=1, max_length=120, description="Nombre para mostrar.", examples=[_EXAMPLE_NAME]
    )


class SubjectOut(ApiModel):
    subject_id: str = Field(
        description="Id interno (UUID). Úsalo en las rutas `/v1/subjects/{subjectId}/…`.",
        examples=[_SUBJECT_ID],
    )
    external_id: str = Field(examples=[_EXAMPLE_EXTERNAL_ID])
    display_name: str = Field(examples=[_EXAMPLE_NAME])
    status: SubjectStatus = Field(description="`ACTIVE` o `INACTIVE` (desactivada).")
    enrollments: int = Field(description="Cantidad de rostros registrados.", examples=[1])
    failed_attempts: int = Field(description="Verificaciones fallidas seguidas.", examples=[0])
    locked_until: datetime | None = Field(
        description="Si tiene valor y es futuro, la persona está bloqueada hasta esa hora (UTC)."
    )
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
    enrollment_id: str = Field(description="Id del rostro registrado.")
    subject_id: str = Field(examples=[_SUBJECT_ID])
    created_at: datetime

    @classmethod
    def of(cls, enrollment: Enrollment) -> EnrollmentOut:
        return cls(
            enrollment_id=enrollment.id,
            subject_id=enrollment.subject_id,
            created_at=enrollment.created_at,
        )


class VerificationOut(ApiModel):
    verification_id: str = Field(description="Id de la operación (aparece en la auditoría).")
    subject_id: str = Field(examples=[_SUBJECT_ID])
    decision: Decision = Field(
        description="`MATCH` es la misma persona · `NO_MATCH` es otra persona · "
        "`INCONCLUSIVE` es zona gris: conviene pedir otra foto."
    )
    score: float = Field(description=_SCORE, examples=[0.9994])
    reason_code: ReasonCode = Field(description="Por qué se tomó la decisión.")

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
    subject_id: str = Field(examples=[_SUBJECT_ID])
    external_id: str = Field(examples=[_EXAMPLE_EXTERNAL_ID])
    display_name: str = Field(examples=[_EXAMPLE_NAME])
    score: float = Field(description=_SCORE, examples=[0.9971])

    @classmethod
    def of(cls, candidate: Candidate) -> CandidateOut:
        return cls(
            subject_id=candidate.subject_id,
            external_id=candidate.external_id,
            display_name=candidate.display_name,
            score=candidate.score,
        )


class IdentificationOut(ApiModel):
    identification_id: str = Field(description="Id de la operación (aparece en la auditoría).")
    decision: Decision = Field(description="Decisión sobre el mejor candidato.")
    reason_code: ReasonCode = Field(
        description="`NO_CANDIDATES` si ninguna persona activa supera el umbral mínimo."
    )
    candidates: list[CandidateOut] = Field(
        description="Personas activas parecidas, de mayor a menor similitud."
    )

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
    action: str = Field(examples=["FACE_VERIFIED"])
    occurred_at: datetime
    subject_id: str | None = Field(examples=[_SUBJECT_ID])
    outcome: str = Field(
        description="`OK`, la decisión (`MATCH`, `NO_MATCH`…) o el `slug` del error.",
        examples=["MATCH"],
    )
    detail: str = Field(examples=["score=0.9994"])
    image_sha256: str | None = Field(
        description="Huella SHA-256 de la imagen enviada. La imagen nunca se guarda."
    )

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
    status: str = Field(description="`UP` o `DEGRADED` (el motor no responde).", examples=["UP"])
    engine: str = Field(description="Motor en uso: `compreface` o `fake`.", examples=["compreface"])
    engine_status: str = Field(examples=["UP"])


class ProblemDetail(BaseModel):
    """Formato de todos los errores (RFC 7807, `application/problem+json`)."""

    type: str = Field(examples=["urn:facial-identity:problem:no_face"])
    title: str = Field(examples=["No se detectó ningún rostro en la imagen"])
    status: int = Field(examples=[422])
    detail: str
    slug: str = Field(
        description="Código estable para que el consumidor decida qué hacer.", examples=["NO_FACE"]
    )
    instance: str = Field(description="Ruta que produjo el error.")
