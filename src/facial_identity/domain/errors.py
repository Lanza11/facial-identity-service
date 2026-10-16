"""Errores tipados del dominio. Cada uno lleva el `slug` y el estado HTTP con el que la API
lo publica como application/problem+json, igual que espera la app móvil."""


class FacialIdentityError(Exception):
    slug = "FACIAL_IDENTITY_ERROR"
    status = 500
    title = "Error del servicio de identidad facial"

    def __init__(self, detail: str | None = None) -> None:
        super().__init__(detail or self.title)
        self.detail = detail or self.title


class SubjectNotFoundError(FacialIdentityError):
    slug = "SUBJECT_NOT_FOUND"
    status = 404
    title = "El sujeto no existe"


class SubjectAlreadyExistsError(FacialIdentityError):
    slug = "SUBJECT_ALREADY_EXISTS"
    status = 409
    title = "Ya existe un sujeto con ese externalId"


class SubjectInactiveError(FacialIdentityError):
    slug = "SUBJECT_INACTIVE"
    status = 409
    title = "El sujeto está desactivado"


class SubjectLockedError(FacialIdentityError):
    slug = "SUBJECT_LOCKED"
    status = 423
    title = "El sujeto está bloqueado temporalmente por intentos fallidos"


class MaxEnrollmentsReachedError(FacialIdentityError):
    slug = "MAX_ENROLLMENTS"
    status = 409
    title = "El sujeto alcanzó el máximo de rostros registrados"


class ConsentRequiredError(FacialIdentityError):
    slug = "CONSENT_REQUIRED"
    status = 409
    title = "La persona no ha autorizado el tratamiento de sus datos biométricos"


class NoEnrollmentsError(FacialIdentityError):
    slug = "NO_ENROLLMENTS"
    status = 409
    title = "El sujeto no tiene rostros registrados"


class InvalidRequestError(FacialIdentityError):
    slug = "VALIDATION_ERROR"
    status = 422
    title = "Solicitud inválida"


class InvalidImageError(FacialIdentityError):
    slug = "INVALID_IMAGE"
    status = 422
    title = "La imagen no es válida"


class NoFaceDetectedError(FacialIdentityError):
    slug = "NO_FACE"
    status = 422
    title = "No se detectó ningún rostro en la imagen"


class MultipleFacesDetectedError(FacialIdentityError):
    slug = "MULTIPLE_FACES"
    status = 422
    title = "Se detectó más de un rostro en la imagen"


class EngineUnavailableError(FacialIdentityError):
    slug = "ENGINE_UNAVAILABLE"
    status = 503
    title = "El motor de reconocimiento no está disponible"


class EngineError(FacialIdentityError):
    slug = "ENGINE_ERROR"
    status = 502
    title = "El motor de reconocimiento respondió con un error"
