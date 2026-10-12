"""Textos y metadatos de la documentación OpenAPI (Swagger en /docs). No contiene lógica."""

from __future__ import annotations

from typing import Any

from facial_identity.api.auth import UnauthorizedError
from facial_identity.api.schemas import ProblemDetail
from facial_identity.config import Settings
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

IMAGE_DESCRIPTION = (
    "Foto con **un solo rostro**, de frente y bien iluminada. JPEG, PNG o WEBP, máximo 5 MB. "
    "Se envía como `multipart/form-data` en el campo `image`."
)


def build_description(settings: Settings) -> str:
    match = settings.fis_match_threshold
    gray = settings.fis_inconclusive_threshold
    return f"""
Servicio independiente de identificación facial (**prototipo**). Cualquier consumidor (app móvil,
web administrativo…) lo usa para registrar rostros y luego comprobarlos. El motor que hace el
reconocimiento (hoy **{settings.fis_engine}**) queda oculto detrás de esta API.

### 🔑 Autenticación: ¿de dónde sale la API key?
Todas las rutas `/v1/*` exigen el header **`x-api-key`**. Su valor es la variable
**`FIS_API_KEY`** del archivo `.env` del servicio (por defecto: **`demo-key`**).

1. Pulsa el botón **Authorize** (arriba a la derecha).
2. Escribe `demo-key` (o tu `FIS_API_KEY`) y pulsa *Authorize*.
3. Desde ese momento Swagger la envía en cada petición.

> ⚠️ No la confundas con `COMPREFACE_API_KEY`: esa es la llave **interna** con la que este
> servicio habla con CompreFace. Los consumidores nunca la ven ni la usan.

### 🚀 Probar el flujo completo en 4 pasos
1. **`POST /v1/subjects`** con `{{"externalId": "CUST-1001", "displayName": "Ana"}}`
   → copia el `subjectId` de la respuesta.
2. **`POST /v1/subjects/{{subjectId}}/enrollments`** → pega el `subjectId` y elige una foto de Ana
   en el campo `image`. Así se registra su rostro.
3. **`POST /v1/subjects/{{subjectId}}/verifications`** → sube **otra** foto. La respuesta dice si
   es Ana.
4. **`POST /v1/identifications`** → sube una foto sin decir de quién es. El servicio busca entre
   todas las personas activas.

### 📸 ¿Cómo viajan las imágenes?
Como archivo en un formulario **`multipart/form-data`**, campo **`image`**: lo mismo que hace un
`<input type="file">` en una página web. No hace falta convertirlas a base64. El servicio no
guarda la foto. El motor extrae del rostro un vector numérico (*embedding*) y las comparaciones
se hacen entre esos vectores.

### 🧮 ¿Cómo se interpreta el resultado?
| `score` (similitud) | `decision` | Significado |
|---|---|---|
| ≥ {match} | `MATCH` | Es la misma persona |
| ≥ {gray} y < {match} | `INCONCLUSIVE` | Zona gris: pedir otra foto |
| < {gray} | `NO_MATCH` | Es otra persona |

### ❗ Errores
Todos los errores usan el formato `application/problem+json` (RFC 7807), con un `slug` estable
(`NO_FACE`, `MULTIPLE_FACES`, `SUBJECT_INACTIVE`, `SUBJECT_LOCKED`…). Cada endpoint lista
abajo los que puede devolver.
"""


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
