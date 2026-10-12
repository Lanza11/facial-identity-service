"""Autenticación del prototipo: una API key compartida por consumidor (backend de la app,
web admin). En producción iría detrás de API Gateway/APIM con credenciales por consumidor."""

from __future__ import annotations

import secrets

from fastapi import Request, Security
from fastapi.security import APIKeyHeader

from facial_identity.domain.errors import FacialIdentityError

_api_key_header = APIKeyHeader(
    name="x-api-key",
    scheme_name="ApiKey",
    description="Valor de `FIS_API_KEY` en el `.env` del servicio (por defecto `demo-key`).",
    auto_error=False,
)


class UnauthorizedError(FacialIdentityError):
    slug = "UNAUTHORIZED"
    status = 401
    title = "API key ausente o inválida"


def require_api_key(request: Request, api_key: str | None = Security(_api_key_header)) -> None:
    expected: str = request.app.state.settings.fis_api_key
    if not api_key or not secrets.compare_digest(api_key, expected):
        raise UnauthorizedError()
