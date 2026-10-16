from __future__ import annotations

from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Path,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)

from facial_identity.api.auth import require_api_key
from facial_identity.api.openapi import (
    IMAGE_DESCRIPTION,
    LIVENESS_DESCRIPTION,
    TAG_AUDIT,
    TAG_ENROLLMENT,
    TAG_HEALTH,
    TAG_RECOGNITION,
    TAG_SUBJECTS,
    problem_responses,
)
from facial_identity.api.schemas import (
    AuditEventOut,
    ConsentCreate,
    ConsentOut,
    EnrollmentOut,
    HealthOut,
    IdentificationOut,
    SubjectCreate,
    SubjectOut,
    VerificationOut,
)
from facial_identity.application.use_cases import FacialIdentityService
from facial_identity.domain.errors import (
    ConsentRequiredError,
    EngineUnavailableError,
    InvalidImageError,
    MaxEnrollmentsReachedError,
    MultipleFacesDetectedError,
    NoEnrollmentsError,
    NoFaceDetectedError,
    SubjectAlreadyExistsError,
    SubjectInactiveError,
    SubjectLockedError,
    SubjectNotFoundError,
)
from facial_identity.domain.models import LivenessResult


def get_service(request: Request) -> FacialIdentityService:
    return request.app.state.service


def read_image(
    request: Request, image: Annotated[UploadFile, File(description=IMAGE_DESCRIPTION)]
) -> bytes:
    if not (image.content_type or "").startswith("image/"):
        raise InvalidImageError("El archivo debe ser una imagen (jpeg, png, webp…)")
    content = image.file.read(request.app.state.settings.fis_max_image_bytes + 1)
    if not content:
        raise InvalidImageError("La imagen está vacía")
    if len(content) > request.app.state.settings.fis_max_image_bytes:
        raise InvalidImageError("La imagen supera el tamaño máximo permitido")
    return content


Service = Annotated[FacialIdentityService, Depends(get_service)]
Image = Annotated[bytes, Depends(read_image)]
SubjectId = Annotated[str, Path(description="El `subjectId` que devolvió `POST /v1/subjects`.")]
Liveness = Annotated[LivenessResult | None, Form(description=LIVENESS_DESCRIPTION)]

_IMAGE_ERRORS = (InvalidImageError, NoFaceDetectedError, MultipleFacesDetectedError)

health_router = APIRouter(tags=[TAG_HEALTH])
router = APIRouter(prefix="/v1", dependencies=[Depends(require_api_key)])


@health_router.get("/health", response_model=HealthOut, summary="Estado del servicio y del motor")
def health(service: Service) -> HealthOut:
    engine_up = service.is_engine_healthy()
    return HealthOut(
        status="UP" if engine_up else "DEGRADED",
        engine=service.engine_name,
        engine_status="UP" if engine_up else "DOWN",
    )


@router.post(
    "/subjects",
    response_model=SubjectOut,
    status_code=status.HTTP_201_CREATED,
    tags=[TAG_SUBJECTS],
    summary="Crear persona",
    description="Da de alta a una persona, todavía sin rostro. Guarda el `subjectId` de la "
    "respuesta: lo necesitas para registrar y verificar su rostro.",
    responses=problem_responses(SubjectAlreadyExistsError),
)
def create_subject(body: SubjectCreate, service: Service) -> SubjectOut:
    subject = service.create_subject(body.external_id, body.display_name)
    return SubjectOut.of(service.summarize_subject(subject.id))


@router.post(
    "/subjects/{subject_id}/consents",
    response_model=ConsentOut,
    status_code=status.HTTP_201_CREATED,
    tags=[TAG_SUBJECTS],
    summary="Registrar la autorización de datos biométricos",
    description="Guarda que la persona autorizó el tratamiento de sus datos biométricos (Ley 1581 "
    "de 2012). Es obligatorio antes de registrar su rostro.",
    responses=problem_responses(SubjectNotFoundError),
)
def record_consent(subject_id: SubjectId, body: ConsentCreate, service: Service) -> ConsentOut:
    return ConsentOut.of(service.record_consent(subject_id, body.text_version, body.channel))


@router.get(
    "/subjects",
    response_model=list[SubjectOut],
    tags=[TAG_SUBJECTS],
    summary="Listar personas",
    responses=problem_responses(),
)
def list_subjects(service: Service) -> list[SubjectOut]:
    return [SubjectOut.of(summary) for summary in service.list_subjects()]


@router.post(
    "/subjects/{subject_id}/deactivate",
    response_model=SubjectOut,
    tags=[TAG_SUBJECTS],
    summary="Desactivar persona",
    description="Baja lógica y reversible: conserva sus rostros, pero no se la puede verificar ni "
    "aparece al identificar hasta que se reactive.",
    responses=problem_responses(SubjectNotFoundError),
)
def deactivate_subject(subject_id: SubjectId, service: Service) -> SubjectOut:
    service.deactivate_subject(subject_id)
    return SubjectOut.of(service.summarize_subject(subject_id))


@router.post(
    "/subjects/{subject_id}/reactivate",
    response_model=SubjectOut,
    tags=[TAG_SUBJECTS],
    summary="Reactivar persona",
    description="Vuelve a activarla y reinicia su contador de intentos fallidos y su bloqueo.",
    responses=problem_responses(SubjectNotFoundError),
)
def reactivate_subject(subject_id: SubjectId, service: Service) -> SubjectOut:
    service.reactivate_subject(subject_id)
    return SubjectOut.of(service.summarize_subject(subject_id))


@router.delete(
    "/subjects/{subject_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=[TAG_SUBJECTS],
    summary="Eliminar persona (supresión total)",
    description="Borra a la persona y todos sus rostros, también dentro del motor. Es "
    "irreversible: corresponde al derecho de supresión de datos. La auditoría se conserva.",
    responses=problem_responses(SubjectNotFoundError, EngineUnavailableError),
)
def delete_subject(subject_id: SubjectId, service: Service) -> Response:
    service.delete_subject(subject_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/subjects/{subject_id}/enrollments",
    response_model=EnrollmentOut,
    status_code=status.HTTP_201_CREATED,
    tags=[TAG_ENROLLMENT],
    summary="Registrar un rostro de la persona",
    description="Sube una foto de la persona. El motor detecta el rostro y guarda su *embedding* "
    "(vector numérico) como referencia. Se permiten varias fotos por persona (hasta el máximo "
    "configurado). Más de una foto ayuda con distintas luces o ángulos. Requiere la autorización "
    "previa de la persona (`POST /v1/subjects/{subjectId}/consents`).",
    responses=problem_responses(
        *_IMAGE_ERRORS,
        SubjectNotFoundError,
        ConsentRequiredError,
        SubjectInactiveError,
        SubjectLockedError,
        MaxEnrollmentsReachedError,
        EngineUnavailableError,
    ),
)
def enroll_face(
    subject_id: SubjectId, image: Image, service: Service, liveness: Liveness = None
) -> EnrollmentOut:
    return EnrollmentOut.of(service.enroll_face(subject_id, image, liveness))


@router.post(
    "/subjects/{subject_id}/verifications",
    response_model=VerificationOut,
    tags=[TAG_RECOGNITION],
    summary="Verificar 1:1: ¿la foto es de esta persona?",
    description="Compara la foto contra **los rostros registrados de esa persona** y devuelve la "
    "mejor similitud y la decisión. Cada `NO_MATCH` suma un intento fallido; al llegar al "
    "máximo, la persona queda bloqueada temporalmente (`SUBJECT_LOCKED`).",
    responses=problem_responses(
        *_IMAGE_ERRORS,
        SubjectNotFoundError,
        SubjectInactiveError,
        NoEnrollmentsError,
        SubjectLockedError,
        EngineUnavailableError,
    ),
)
def verify_face(
    subject_id: SubjectId, image: Image, service: Service, liveness: Liveness = None
) -> VerificationOut:
    return VerificationOut.of(service.verify_face(subject_id, image, liveness))


@router.post(
    "/identifications",
    response_model=IdentificationOut,
    tags=[TAG_RECOGNITION],
    summary="Identificar 1:N: ¿de quién es la foto?",
    description="Busca el rostro entre **todas las personas activas**, sin indicar quién es. "
    "Devuelve los candidatos que superan el umbral mínimo, ordenados por similitud.",
    responses=problem_responses(*_IMAGE_ERRORS, EngineUnavailableError),
)
def identify_face(image: Image, service: Service, liveness: Liveness = None) -> IdentificationOut:
    return IdentificationOut.of(service.identify_face(image, liveness))


@router.get(
    "/audit",
    response_model=list[AuditEventOut],
    tags=[TAG_AUDIT],
    summary="Consultar la auditoría",
    description="Eventos más recientes primero. Incluye éxitos y errores. Nunca incluye la "
    "imagen, solo su hash SHA-256.",
    responses=problem_responses(),
)
def list_audit(
    service: Service,
    subject_id: Annotated[
        str | None, Query(alias="subjectId", description="Filtra por persona (opcional).")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=500, description="Máximo de eventos.")] = 100,
) -> list[AuditEventOut]:
    return [AuditEventOut.of(e) for e in service.audit_events(subject_id, limit)]
