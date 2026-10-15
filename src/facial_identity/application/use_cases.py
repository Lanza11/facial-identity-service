from __future__ import annotations

import hashlib
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

from facial_identity.domain.errors import (
    ConsentRequiredError,
    FacialIdentityError,
    MaxEnrollmentsReachedError,
    NoEnrollmentsError,
    SubjectAlreadyExistsError,
    SubjectInactiveError,
    SubjectLockedError,
    SubjectNotFoundError,
)
from facial_identity.domain.models import (
    AuditAction,
    AuditEvent,
    Candidate,
    Consent,
    Decision,
    EngineMatch,
    Enrollment,
    IdentificationResult,
    LivenessResult,
    ReasonCode,
    Subject,
    SubjectStatus,
    SubjectSummary,
    VerificationResult,
)
from facial_identity.domain.policies import EnrollmentPolicy, LockoutPolicy, MatchPolicy
from facial_identity.ports import AuditLog, Clock, FaceEngine, SubjectRepository

T = TypeVar("T")


@dataclass(frozen=True)
class Policies:
    match: MatchPolicy
    enrollment: EnrollmentPolicy
    lockout: LockoutPolicy
    max_identify_candidates: int


def _new_id() -> str:
    return str(uuid.uuid4())


def _sha256(image: bytes) -> str:
    return hashlib.sha256(image).hexdigest()


class FacialIdentityService:
    """Casos de uso del servicio. Orquesta motor, repositorio y auditoría aplicando las reglas
    de negocio; no conoce HTTP ni CompreFace."""

    def __init__(
        self,
        engine: FaceEngine,
        subjects: SubjectRepository,
        audit: AuditLog,
        clock: Clock,
        policies: Policies,
    ) -> None:
        self._engine = engine
        self._subjects = subjects
        self._audit = audit
        self._clock = clock
        self._policies = policies

    @property
    def engine_name(self) -> str:
        return self._engine.name

    def create_subject(self, external_id: str, display_name: str) -> Subject:
        if self._subjects.get_by_external_id(external_id):
            raise SubjectAlreadyExistsError()
        subject = Subject(
            id=_new_id(),
            external_id=external_id,
            display_name=display_name,
            status=SubjectStatus.ACTIVE,
            created_at=self._clock.now(),
        )
        self._subjects.add(subject)
        self._record(AuditAction.SUBJECT_CREATED, subject.id)
        return subject

    def list_subjects(self) -> list[SubjectSummary]:
        return [self._summarize(s) for s in self._subjects.list_all()]

    def summarize_subject(self, subject_id: str) -> SubjectSummary:
        return self._summarize(self.get_subject(subject_id))

    def record_consent(self, subject_id: str, text_version: str, channel: str) -> Consent:
        subject = self.get_subject(subject_id)
        consent = Consent(_new_id(), subject.id, text_version, channel, self._clock.now())
        self._subjects.add_consent(consent)
        self._record(
            AuditAction.CONSENT_GRANTED,
            subject.id,
            detail=f"texto={text_version} canal={channel}",
        )
        return consent

    def get_subject(self, subject_id: str) -> Subject:
        subject = self._subjects.get(subject_id)
        if subject is None:
            raise SubjectNotFoundError()
        return subject

    def enroll_face(
        self, subject_id: str, image: bytes, liveness: LivenessResult | None = None
    ) -> Enrollment:
        image_hash = _sha256(image)
        return self._audited(
            AuditAction.FACE_ENROLLED,
            subject_id,
            image_hash,
            lambda: self._enroll(subject_id, image, image_hash),
            liveness=liveness,
        )

    def verify_face(
        self, subject_id: str, image: bytes, liveness: LivenessResult | None = None
    ) -> VerificationResult:
        return self._audited(
            AuditAction.FACE_VERIFIED,
            subject_id,
            _sha256(image),
            lambda: self._verify(subject_id, image),
            outcome_of=lambda r: r.decision.value,
            detail_of=lambda r: f"score={r.score:.4f}",
            liveness=liveness,
        )

    def identify_face(
        self, image: bytes, liveness: LivenessResult | None = None
    ) -> IdentificationResult:
        return self._audited(
            AuditAction.FACE_IDENTIFIED,
            None,
            _sha256(image),
            lambda: self._identify(image),
            outcome_of=lambda r: r.decision.value,
            detail_of=lambda r: f"candidates={len(r.candidates)}",
            liveness=liveness,
        )

    def deactivate_subject(self, subject_id: str) -> Subject:
        return self._change_status(subject_id, SubjectStatus.INACTIVE)

    def reactivate_subject(self, subject_id: str) -> Subject:
        return self._change_status(subject_id, SubjectStatus.ACTIVE)

    def delete_subject(self, subject_id: str) -> None:
        subject = self.get_subject(subject_id)
        self._engine.remove_subject(subject.id)
        self._subjects.delete(subject.id)
        self._record(AuditAction.SUBJECT_DELETED, subject.id, detail="supresión total")

    def audit_events(self, subject_id: str | None = None, limit: int = 100) -> list[AuditEvent]:
        return self._audit.list_events(subject_id, limit)

    def is_engine_healthy(self) -> bool:
        return self._engine.is_healthy()

    def _enroll(self, subject_id: str, image: bytes, image_hash: str) -> Enrollment:
        subject = self._require_usable_subject(subject_id)
        if self._subjects.latest_consent(subject.id) is None:
            raise ConsentRequiredError()
        current = len(self._subjects.list_enrollments(subject.id))
        if not self._policies.enrollment.can_enroll(current):
            raise MaxEnrollmentsReachedError()
        enrollment = Enrollment(
            id=_new_id(),
            subject_id=subject.id,
            engine_face_id=self._engine.enroll(subject.id, image),
            image_sha256=image_hash,
            created_at=self._clock.now(),
        )
        self._subjects.add_enrollment(enrollment)
        return enrollment

    def _verify(self, subject_id: str, image: bytes) -> VerificationResult:
        subject = self._require_usable_subject(subject_id)
        enrollments = self._subjects.list_enrollments(subject.id)
        if not enrollments:
            raise NoEnrollmentsError()
        score = max(self._engine.verify(e.engine_face_id, image) for e in enrollments)
        decision, reason = self._policies.match.decide(score)
        self._register_attempt(subject, decision)
        return VerificationResult(_new_id(), subject.id, decision, round(score, 4), reason)

    def _identify(self, image: bytes) -> IdentificationResult:
        matches = self._engine.identify(image, self._policies.max_identify_candidates)
        candidates = sorted(
            (c for c in map(self._to_candidate, matches) if c is not None),
            key=lambda c: c.score,
            reverse=True,
        )
        if not candidates:
            return IdentificationResult(_new_id(), Decision.NO_MATCH, ReasonCode.NO_CANDIDATES, [])
        decision, reason = self._policies.match.decide(candidates[0].score)
        return IdentificationResult(_new_id(), decision, reason, candidates)

    def _to_candidate(self, match: EngineMatch) -> Candidate | None:
        subject = self._subjects.get(match.engine_subject)
        if subject is None or not subject.is_active:
            return None
        if not self._policies.match.is_candidate(match.similarity):
            return None
        return Candidate(
            subject.id, subject.external_id, subject.display_name, round(match.similarity, 4)
        )

    def _summarize(self, subject: Subject) -> SubjectSummary:
        consent = self._subjects.latest_consent(subject.id)
        return SubjectSummary(
            subject=subject,
            enrollments=len(self._subjects.list_enrollments(subject.id)),
            consented_at=consent.granted_at if consent else None,
        )

    def _require_usable_subject(self, subject_id: str) -> Subject:
        subject = self.get_subject(subject_id)
        if not subject.is_active:
            raise SubjectInactiveError()
        if subject.is_locked(self._clock.now()):
            raise SubjectLockedError()
        return subject

    def _register_attempt(self, subject: Subject, decision: Decision) -> None:
        if decision is Decision.MATCH:
            self._subjects.update(subject.with_attempts_reset())
        elif decision is Decision.NO_MATCH:
            locked_until = self._policies.lockout.locked_until_after_failure(
                subject.failed_attempts, self._clock.now()
            )
            self._subjects.update(subject.with_failed_attempt(locked_until))

    def _change_status(self, subject_id: str, status: SubjectStatus) -> Subject:
        subject = self.get_subject(subject_id).with_status(status).with_attempts_reset()
        self._subjects.update(subject)
        action = (
            AuditAction.SUBJECT_DEACTIVATED
            if status is SubjectStatus.INACTIVE
            else AuditAction.SUBJECT_REACTIVATED
        )
        self._record(action, subject.id)
        return subject

    def _audited(
        self,
        action: AuditAction,
        subject_id: str | None,
        image_hash: str,
        operation: Callable[[], T],
        outcome_of: Callable[[T], str] = lambda _: "OK",
        detail_of: Callable[[T], str] = lambda _: "",
        liveness: LivenessResult | None = None,
    ) -> T:
        liveness_detail = f"liveness={liveness.value}" if liveness else ""
        try:
            result = operation()
        except FacialIdentityError as error:
            self._record(
                action,
                subject_id,
                outcome=error.slug,
                detail=liveness_detail,
                image_hash=image_hash,
            )
            raise
        self._record(
            action,
            subject_id,
            outcome=outcome_of(result),
            detail=" ".join(filter(None, [detail_of(result), liveness_detail])),
            image_hash=image_hash,
        )
        return result

    def _record(
        self,
        action: AuditAction,
        subject_id: str | None,
        outcome: str = "OK",
        detail: str = "",
        image_hash: str | None = None,
    ) -> None:
        self._audit.record(
            AuditEvent(
                id=_new_id(),
                action=action,
                occurred_at=self._clock.now(),
                subject_id=subject_id,
                outcome=outcome,
                detail=detail,
                image_sha256=image_hash,
            )
        )
