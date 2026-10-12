"""Errores como application/problem+json (RFC 7807) con `slug`, el formato que ya traduce
`problem_translator.dart` en la app móvil."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from facial_identity.domain.errors import FacialIdentityError

_MEDIA_TYPE = "application/problem+json"


def problem(status: int, slug: str, title: str, detail: str, instance: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        media_type=_MEDIA_TYPE,
        content={
            "type": f"urn:facial-identity:problem:{slug.lower()}",
            "title": title,
            "status": status,
            "detail": detail,
            "slug": slug,
            "instance": instance,
        },
    )


def register_problem_handlers(app: FastAPI) -> None:
    @app.exception_handler(FacialIdentityError)
    async def _domain_error(request: Request, error: FacialIdentityError) -> JSONResponse:
        return problem(error.status, error.slug, error.title, error.detail, request.url.path)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, error: RequestValidationError) -> JSONResponse:
        detail = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in error.errors())
        return problem(422, "VALIDATION_ERROR", "Solicitud inválida", detail, request.url.path)
