from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from facial_identity.domain.models import Decision, ReasonCode


@dataclass(frozen=True)
class MatchPolicy:
    """Traduce una similitud del motor a una decisión de negocio. La zona gris evita aceptar
    o rechazar en falso cuando el motor no es concluyente."""

    match_threshold: float
    inconclusive_threshold: float

    def __post_init__(self) -> None:
        if not 0 <= self.inconclusive_threshold <= self.match_threshold <= 1:
            raise ValueError("Se requiere 0 <= inconclusive_threshold <= match_threshold <= 1")

    def decide(self, score: float) -> tuple[Decision, ReasonCode]:
        if score >= self.match_threshold:
            return Decision.MATCH, ReasonCode.SCORE_ABOVE_THRESHOLD
        if score >= self.inconclusive_threshold:
            return Decision.INCONCLUSIVE, ReasonCode.SCORE_IN_GRAY_ZONE
        return Decision.NO_MATCH, ReasonCode.SCORE_BELOW_THRESHOLD

    def is_candidate(self, score: float) -> bool:
        return score >= self.inconclusive_threshold


@dataclass(frozen=True)
class EnrollmentPolicy:
    max_enrollments: int

    def can_enroll(self, current_enrollments: int) -> bool:
        return current_enrollments < self.max_enrollments


@dataclass(frozen=True)
class LockoutPolicy:
    """Bloquea temporalmente a un sujeto tras varias verificaciones fallidas seguidas."""

    max_failed_attempts: int
    lockout: timedelta

    def locked_until_after_failure(self, failed_attempts: int, now: datetime) -> datetime | None:
        if failed_attempts + 1 >= self.max_failed_attempts:
            return now + self.lockout
        return None
