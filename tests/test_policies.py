from datetime import UTC, datetime, timedelta

import pytest

from facial_identity.domain.models import Decision, ReasonCode
from facial_identity.domain.policies import EnrollmentPolicy, LockoutPolicy, MatchPolicy

POLICY = MatchPolicy(match_threshold=0.9, inconclusive_threshold=0.8)


@pytest.mark.parametrize(
    ("score", "decision", "reason"),
    [
        (0.95, Decision.MATCH, ReasonCode.SCORE_ABOVE_THRESHOLD),
        (0.90, Decision.MATCH, ReasonCode.SCORE_ABOVE_THRESHOLD),
        (0.85, Decision.INCONCLUSIVE, ReasonCode.SCORE_IN_GRAY_ZONE),
        (0.40, Decision.NO_MATCH, ReasonCode.SCORE_BELOW_THRESHOLD),
    ],
)
def test_match_policy_decide_por_umbrales(score, decision, reason):
    assert POLICY.decide(score) == (decision, reason)


def test_match_policy_rechaza_umbrales_incoherentes():
    with pytest.raises(ValueError):
        MatchPolicy(match_threshold=0.7, inconclusive_threshold=0.8)


def test_enrollment_policy_limita_registros():
    policy = EnrollmentPolicy(max_enrollments=3)
    assert policy.can_enroll(2)
    assert not policy.can_enroll(3)


def test_lockout_policy_bloquea_al_alcanzar_el_maximo():
    now = datetime(2026, 1, 1, tzinfo=UTC)
    policy = LockoutPolicy(max_failed_attempts=3, lockout=timedelta(minutes=10))
    assert policy.locked_until_after_failure(failed_attempts=1, now=now) is None
    assert policy.locked_until_after_failure(failed_attempts=2, now=now) == now + timedelta(
        minutes=10
    )
