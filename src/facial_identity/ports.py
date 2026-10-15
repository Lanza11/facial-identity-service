"""Puertos (contratos) que la aplicación necesita. Cambiar de motor = escribir otro adaptador
que cumpla `FaceEngine`; los casos de uso, la API y las reglas no cambian."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from facial_identity.domain.models import AuditEvent, Consent, EngineMatch, Enrollment, Subject


class FaceEngine(Protocol):
    name: str

    def enroll(self, engine_subject: str, image: bytes) -> str:
        """Registra el rostro (exactamente uno) y devuelve el id del rostro en el motor."""

    def verify(self, engine_face_id: str, image: bytes) -> float:
        """Similitud 0..1 entre el rostro registrado y el rostro (único) de la imagen."""

    def identify(self, image: bytes, max_candidates: int) -> list[EngineMatch]:
        """Sujetos del motor más parecidos al rostro (único) de la imagen."""

    def remove_subject(self, engine_subject: str) -> None: ...

    def is_healthy(self) -> bool: ...


class SubjectRepository(Protocol):
    def add(self, subject: Subject) -> None: ...

    def update(self, subject: Subject) -> None: ...

    def delete(self, subject_id: str) -> None: ...

    def get(self, subject_id: str) -> Subject | None: ...

    def get_by_external_id(self, external_id: str) -> Subject | None: ...

    def list_all(self) -> list[Subject]: ...

    def add_enrollment(self, enrollment: Enrollment) -> None: ...

    def list_enrollments(self, subject_id: str) -> list[Enrollment]: ...

    def add_consent(self, consent: Consent) -> None: ...

    def latest_consent(self, subject_id: str) -> Consent | None: ...


class AuditLog(Protocol):
    def record(self, event: AuditEvent) -> None: ...

    def list_events(self, subject_id: str | None = None, limit: int = 100) -> list[AuditEvent]: ...


class Clock(Protocol):
    def now(self) -> datetime: ...
