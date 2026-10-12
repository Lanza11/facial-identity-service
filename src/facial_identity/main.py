"""Composición de la aplicación: el único lugar que decide qué adaptadores se usan."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from facial_identity.adapters.compreface_engine import CompreFaceEngine
from facial_identity.adapters.fake_engine import FakeFaceEngine
from facial_identity.adapters.sqlite_store import SqliteStore
from facial_identity.api.openapi import DESCRIPTION, SWAGGER_UI_PARAMETERS, TAGS
from facial_identity.api.problems import register_problem_handlers
from facial_identity.api.routes import health_router, router
from facial_identity.application.use_cases import FacialIdentityService, Policies
from facial_identity.config import Settings
from facial_identity.domain.policies import EnrollmentPolicy, LockoutPolicy, MatchPolicy
from facial_identity.ports import FaceEngine

_DEMO_DIR = Path(__file__).resolve().parents[2] / "demo"


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


def build_engine(settings: Settings) -> FaceEngine:
    if settings.fis_engine == "fake":
        return FakeFaceEngine()
    return CompreFaceEngine(
        base_url=settings.compreface_url,
        api_key=settings.compreface_api_key,
        det_prob_threshold=settings.compreface_det_prob_threshold,
    )


def build_policies(settings: Settings) -> Policies:
    return Policies(
        match=MatchPolicy(settings.fis_match_threshold, settings.fis_inconclusive_threshold),
        enrollment=EnrollmentPolicy(settings.fis_max_enrollments),
        lockout=LockoutPolicy(
            settings.fis_max_failed_attempts, timedelta(minutes=settings.fis_lockout_minutes)
        ),
        max_identify_candidates=settings.fis_identify_candidates,
    )


def build_service(settings: Settings, db_path: str | None = None) -> FacialIdentityService:
    if db_path is None:
        settings.fis_data_dir.mkdir(parents=True, exist_ok=True)
        db_path = str(settings.db_path)
    store = SqliteStore(db_path)
    return FacialIdentityService(
        engine=build_engine(settings),
        subjects=store,
        audit=store,
        clock=SystemClock(),
        policies=build_policies(settings),
    )


def create_app(
    settings: Settings | None = None, service: FacialIdentityService | None = None
) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(
        title="facial-identity-service",
        version="0.1.0",
        description=DESCRIPTION,
        openapi_tags=TAGS,
        swagger_ui_parameters=SWAGGER_UI_PARAMETERS,
    )
    app.state.settings = settings
    app.state.service = service or build_service(settings)
    register_problem_handlers(app)
    app.include_router(health_router)
    app.include_router(router)
    if _DEMO_DIR.is_dir():
        app.mount("/demo", StaticFiles(directory=_DEMO_DIR, html=True), name="demo")

        @app.get("/", include_in_schema=False)
        def _root() -> RedirectResponse:
            return RedirectResponse("/demo/")

    return app
