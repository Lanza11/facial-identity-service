"""Textos y metadatos de la documentación OpenAPI (Swagger en /docs). No contiene lógica."""

from __future__ import annotations

from typing import Any

from facial_identity.api.auth import UnauthorizedError
from facial_identity.api.schemas import ProblemDetail
from facial_identity.domain.errors import FacialIdentityError, InvalidRequestError

TAG_HEALTH = "Salud"
TAG_SUBJECTS = "1 · Personas"
TAG_ENROLLMENT = "2 · Registro de rostros"
TAG_RECOGNITION = "3 · Reconocimiento"
TAG_AUDIT = "4 · Auditoría"

TAGS: list[dict[str, str]] = [
    {
        "name": TAG_SUBJECTS,
        "description": "Alta, consulta, desactivación y eliminación de las personas. "
        "**Empieza aquí:** crea la persona y copia su `subjectId`.",
    },
    {
        "name": TAG_ENROLLMENT,
        "description": "Guarda el rostro de una persona a partir de una foto. "
        "Es su *referencia* para compararla después.",
    },
    {
        "name": TAG_RECOGNITION,
        "description": "Compara una foto nueva contra los rostros registrados: "
        "**verificar** (¿es esta persona?) o **identificar** (¿quién es?).",
    },
    {"name": TAG_AUDIT, "description": "Historial de todas las operaciones."},
    {"name": TAG_HEALTH, "description": "Estado del servicio y del motor. No requiere API key."},
]

SWAGGER_UI_PARAMETERS: dict[str, Any] = {
    "persistAuthorization": True,
    "docExpansion": "list",
    "displayRequestDuration": True,
    "tryItOutEnabled": True,
    "defaultModelsExpandDepth": 0,
}

LIVENESS_DESCRIPTION = (
    "Opcional. Resultado de la prueba de vida hecha en el dispositivo (parpadeo y giro de "
    "cabeza): `PASSED`, `FAILED` o `NOT_PERFORMED`. Se guarda en la auditoría."
)

IMAGE_DESCRIPTION = (
    "Foto con **un solo rostro**, de frente y bien iluminada. JPEG, PNG o WEBP, máximo 5 MB. "
    "Se envía como `multipart/form-data` en el campo `image`."
)


DESCRIPTION = (
    "Servicio independiente de identificación facial (prototipo). Registra, verifica (1:1) e "
    "identifica (1:N) rostros sobre un motor intercambiable."
)


def problem_responses(*errors: type[FacialIdentityError]) -> dict[int | str, dict[str, Any]]:
    """Documenta los errores que puede devolver un endpoint, agrupados por estado HTTP y con un
    ejemplo por `slug`. Siempre incluye el 401 (API key) y el 422 de validación de la petición."""
    responses: dict[int | str, dict[str, Any]] = {}
    for error in (UnauthorizedError, InvalidRequestError, *errors):
        response = responses.setdefault(
            error.status,
            {
                "description": error.title,
                "content": {
                    "application/problem+json": {
                        "schema": ProblemDetail.model_json_schema(),
                        "examples": {},
                    }
                },
            },
        )
        if error.title not in response["description"]:
            response["description"] += f" · {error.title}"
        response["content"]["application/problem+json"]["examples"][error.slug] = {
            "summary": error.title,
            "value": {
                "type": f"urn:facial-identity:problem:{error.slug.lower()}",
                "title": error.title,
                "status": error.status,
                "detail": error.title,
                "slug": error.slug,
                "instance": "/v1/…",
            },
        }
    return responses
