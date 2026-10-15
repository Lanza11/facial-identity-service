# facial-identity-service

Prototipo de un **servicio independiente de identificación facial**. Expone una API propia y estable para:
- registrar rostros de personas;
- verificarlos (1:1) e identificarlos (1:N);
- desactivarlos o eliminarlos.

Por debajo usa un motor de reconocimiento intercambiable; hoy es [CompreFace](https://github.com/exadel-inc/CompreFace) 1.2.0.

> **Estado:** prototipo de investigación de viabilidad. No está pensado para producción: la prueba de vida corre solo en el navegador de la demo, la autenticación es simple y no hay despliegue en nube. Ver [docs/ANALISIS.md](docs/ANALISIS.md).

La demo (`/demo`) cuenta tres escenarios del negocio con identidad visual propia, captura guiada y **prueba de vida** (parpadeo y giro de cabeza) hecha con [MediaPipe Face Landmarker](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker/web_js) de Google. Lo técnico (Swagger, personas, auditoría, llamadas a la API) aparece al activar el interruptor **Modo técnico**.

## Arquitectura

```
Consumidor (app móvil / web admin / demo)
        │  API v1 normalizada (x-api-key, problem+json)
        ▼
facial-identity-service (FastAPI)
  api/          → contrato HTTP y errores RFC 7807
  application/  → casos de uso + auditoría
  domain/       → modelos, reglas (umbrales, límites, bloqueo) y errores
  ports.py      → FaceEngine, SubjectRepository, AuditLog
  adapters/     → compreface_engine | fake_engine | sqlite_store
        │  UUID opaco por persona (el motor nunca ve nombres ni cédulas)
        ▼
CompreFace (api + core ML + postgres + admin/ui)
```

Para cambiar de motor basta con escribir otro adaptador de `FaceEngine` y seleccionarlo en `main.py` con `FIS_ENGINE`.

## Requisitos

- Docker Desktop con Compose v2.
- CPU x86 con AVX2. El build `mobilenet` lo necesita; con AVX a secas usa `COMPREFACE_CORE_TAG=1.2.0`.
- Unos 6 GB de RAM libres.
- Python 3.11+ (solo para el script de bootstrap y los tests).

## Puesta en marcha

```powershell
python -m venv .venv; .venv\Scripts\pip install -e ".[dev]"
copy .env.example .env
docker compose up -d                                   # CompreFace + fachada
.venv\Scripts\python scripts\bootstrap_compreface.py   # crea app/servicio en CompreFace y guarda la API key en .env
docker compose up -d facade                            # recarga la fachada con la key
```

La imagen de la fachada descarga MediaPipe (~40 MB) al construirse. Para ejecutar la fachada fuera de Docker, descárgalo una vez con `.venv\Scripts\python scripts\fetch_mediapipe.py`; queda en `demo/vendor/`, fuera de git. Así la demo funciona sin internet, salvo las fuentes tipográficas, que tienen respaldo del sistema.

| URL | Qué es |
|---|---|
| <http://localhost:8080/demo/> | Demo con los tres escenarios |
| <http://localhost:8080/docs> | Swagger / OpenAPI del servicio |
| <http://localhost:8080/health> | Salud del servicio y del motor |
| <http://localhost:8000> | UI de CompreFace (`demo@fis.local` / `Demo12345!`) |

Guion de la demo: [docs/DEMO.md](docs/DEMO.md). Cómo funciona por dentro (frontend, backend, imágenes y API keys): [docs/ARQUITECTURA.md](docs/ARQUITECTURA.md).

> **¿Qué API key pongo en Swagger?** La de `FIS_API_KEY` del `.env` (por defecto `demo-key`): botón **Authorize** en <http://localhost:8080/docs>. La `COMPREFACE_API_KEY` es interna y no se usa desde fuera.

### Ejecutar la fachada fuera de Docker

```powershell
docker compose up -d compreface-postgres-db compreface-api compreface-admin compreface-core compreface-fe
.venv\Scripts\uvicorn facial_identity.main:create_app --factory --port 8080
```

## API v1

Todas las rutas `/v1` requieren el header `x-api-key`.

| Método | Ruta | Descripción |
|---|---|---|
| `POST` | `/v1/subjects` | Crear persona `{externalId, displayName}` |
| `GET` | `/v1/subjects` | Listar personas |
| `POST` | `/v1/subjects/{id}/consents` | Registrar la autorización de datos biométricos `{textVersion, channel}` |
| `POST` | `/v1/subjects/{id}/enrollments` | Registrar rostro (multipart `image`). Exige autorización previa |
| `POST` | `/v1/subjects/{id}/verifications` | Verificar 1:1 → `{decision, score, reasonCode}` |
| `POST` | `/v1/identifications` | Identificar 1:N → `{decision, candidates[]}` |
| `POST` | `/v1/subjects/{id}/deactivate` · `/reactivate` | Desactivar o reactivar (lógico) |
| `DELETE` | `/v1/subjects/{id}` | Supresión total (también en el motor) |
| `GET` | `/v1/audit?subjectId=` | Auditoría |
| `GET` | `/health` | Salud (pública) |

`decision` puede ser `MATCH`, `NO_MATCH` o `INCONCLUSIVE` (zona gris entre umbrales). Los tres endpoints con imagen aceptan además el campo opcional `liveness` (`PASSED`, `FAILED` o `NOT_PERFORMED`): el resultado de la prueba de vida hecha en el dispositivo, que se guarda en la auditoría. Los errores son `application/problem+json` con estos `slug`:

| `slug` | Cuándo |
|---|---|
| `NO_FACE` | No hay ningún rostro en la imagen |
| `MULTIPLE_FACES` | Hay más de un rostro |
| `SUBJECT_INACTIVE` | La persona está desactivada |
| `SUBJECT_LOCKED` | La persona está bloqueada por intentos fallidos |
| `MAX_ENROLLMENTS` | Se alcanzó el máximo de rostros por persona |
| `NO_ENROLLMENTS` | La persona no tiene rostros registrados |
| `CONSENT_REQUIRED` | La persona no ha autorizado el uso de sus datos biométricos |
| `INVALID_IMAGE` | El archivo no es una imagen válida |
| `ENGINE_UNAVAILABLE` | El motor no responde |
| `UNAUTHORIZED` | Falta la API key o es inválida |

## Configuración

Toda la configuración va por variables de entorno; ver [.env.example](.env.example).

| Variable | Default | Uso |
|---|---|---|
| `FIS_ENGINE` | `compreface` | `compreface` o `fake` |
| `FIS_API_KEY` | `demo-key` | Key que deben enviar los consumidores |
| `FIS_MATCH_THRESHOLD` / `FIS_INCONCLUSIVE_THRESHOLD` | `0.90` / `0.80` | Umbrales de decisión |
| `FIS_MAX_ENROLLMENTS` | `3` | Rostros por persona |
| `FIS_MAX_FAILED_ATTEMPTS` / `FIS_LOCKOUT_MINUTES` | `5` / `15` | Bloqueo tras fallos |
| `COMPREFACE_API_KEY` | — | Key del servicio de reconocimiento de CompreFace |
| `COMPREFACE_CORE_TAG` | `1.2.0-mobilenet` | Build del modelo |

## Desarrollo

```powershell
.venv\Scripts\pytest          # tests de dominio, casos de uso y API (motor simulado, sin Docker)
.venv\Scripts\ruff check .
.venv\Scripts\ruff format .
```

## Datos y privacidad

- No se guardan imágenes: CompreFace corre con `SAVE_IMAGES_TO_DB=false` y la auditoría solo guarda el hash SHA‑256.
- El motor solo conoce un UUID por persona.
- Sin autorización registrada (`/consents`) no se puede registrar el rostro de nadie.
- La comparación "foto registrada / foto de ahora" de la demo guarda miniaturas solo en el `localStorage` del navegador que hace la demo. El servicio no las recibe ni las guarda.
- `.gitignore` excluye `.env`, bases locales e imágenes. **No subas fotos al repositorio.**
- Los modelos de CompreFace son pre‑entrenados y de uso de investigación no comercial: válidos para este prototipo, pero deben revisarse antes de producción.
