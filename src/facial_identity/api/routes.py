from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, Request, Response, UploadFile, status

from facial_identity.api.auth import require_api_key
from facial_identity.api.schemas import (
    AuditEventOut,
    EnrollmentOut,
    HealthOut,
    IdentificationOut,
    SubjectCreate,
    SubjectOut,
    VerificationOut,
)
from facial_identity.application.use_cases import FacialIdentityService
from facial_identity.domain.errors import InvalidImageError


def get_service(request: Request) -> FacialIdentityService:
    return request.app.state.service


def read_image(request: Request, image: Annotated[UploadFile, File()]) -> bytes:
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

health_router = APIRouter(tags=["health"])
router = APIRouter(prefix="/v1", dependencies=[Depends(require_api_key)])


@health_router.get("/health", response_model=HealthOut)
def health(service: Service) -> HealthOut:
    engine_up = service.is_engine_healthy()
    return HealthOut(
        status="UP" if engine_up else "DEGRADED",
        engine=service.engine_name,
        engine_status="UP" if engine_up else "DOWN",
    )


@router.post(
    "/subjects", response_model=SubjectOut, status_code=status.HTTP_201_CREATED, tags=["subjects"]
)
def create_subject(body: SubjectCreate, service: Service) -> SubjectOut:
    return SubjectOut.of(service.create_subject(body.external_id, body.display_name), 0)


@router.get("/subjects", response_model=list[SubjectOut], tags=["subjects"])
def list_subjects(service: Service) -> list[SubjectOut]:
    return [SubjectOut.of(subject, count) for subject, count in service.list_subjects()]


@router.post("/subjects/{subject_id}/deactivate", response_model=SubjectOut, tags=["subjects"])
def deactivate_subject(subject_id: str, service: Service) -> SubjectOut:
    subject = service.deactivate_subject(subject_id)
    return SubjectOut.of(subject, service.count_enrollments(subject.id))


@router.post("/subjects/{subject_id}/reactivate", response_model=SubjectOut, tags=["subjects"])
def reactivate_subject(subject_id: str, service: Service) -> SubjectOut:
    subject = service.reactivate_subject(subject_id)
    return SubjectOut.of(subject, service.count_enrollments(subject.id))


@router.delete("/subjects/{subject_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["subjects"])
def delete_subject(subject_id: str, service: Service) -> Response:
    service.delete_subject(subject_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/subjects/{subject_id}/enrollments",
    response_model=EnrollmentOut,
    status_code=status.HTTP_201_CREATED,
    tags=["faces"],
)
def enroll_face(subject_id: str, image: Image, service: Service) -> EnrollmentOut:
    return EnrollmentOut.of(service.enroll_face(subject_id, image))


@router.post("/subjects/{subject_id}/verifications", response_model=VerificationOut, tags=["faces"])
def verify_face(subject_id: str, image: Image, service: Service) -> VerificationOut:
    return VerificationOut.of(service.verify_face(subject_id, image))


@router.post("/identifications", response_model=IdentificationOut, tags=["faces"])
def identify_face(image: Image, service: Service) -> IdentificationOut:
    return IdentificationOut.of(service.identify_face(image))


@router.get("/audit", response_model=list[AuditEventOut], tags=["audit"])
def list_audit(
    service: Service,
    subject_id: Annotated[str | None, Query(alias="subjectId")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[AuditEventOut]:
    return [AuditEventOut.of(e) for e in service.audit_events(subject_id, limit)]
