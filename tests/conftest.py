from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from facial_identity.adapters.fake_engine import FakeFaceEngine
from facial_identity.adapters.sqlite_store import SqliteStore
from facial_identity.application.use_cases import FacialIdentityService, Policies
from facial_identity.config import Settings
from facial_identity.domain.policies import EnrollmentPolicy, LockoutPolicy, MatchPolicy
from facial_identity.main import create_app

API_KEY = "test-key"
FACE_ANA = b"\xff\xd8 rostro de ana"
FACE_ANA_2 = b"\xff\xd8 otra foto de ana"
FACE_LUIS = b"\xff\xd8 rostro de luis"


class FixedClock:
    def __init__(self) -> None:
        self.current = datetime(2026, 10, 11, 12, 0, tzinfo=UTC)

    def now(self) -> datetime:
        return self.current

    def advance(self, minutes: int) -> None:
        self.current += timedelta(minutes=minutes)


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock()


@pytest.fixture
def service(clock: FixedClock) -> FacialIdentityService:
    store = SqliteStore(":memory:")
    return FacialIdentityService(
        engine=FakeFaceEngine(),
        subjects=store,
        audit=store,
        clock=clock,
        policies=Policies(
            match=MatchPolicy(match_threshold=0.9, inconclusive_threshold=0.8),
            enrollment=EnrollmentPolicy(max_enrollments=2),
            lockout=LockoutPolicy(max_failed_attempts=3, lockout=timedelta(minutes=15)),
            max_identify_candidates=3,
        ),
    )


@pytest.fixture
def client(service: FacialIdentityService) -> TestClient:
    settings = Settings(fis_engine="fake", fis_api_key=API_KEY, _env_file=None)
    app = create_app(settings=settings, service=service)
    return TestClient(app, headers={"x-api-key": API_KEY})
