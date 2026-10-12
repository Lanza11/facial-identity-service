import pytest

from facial_identity.adapters.fake_engine import MULTIPLE_FACES_MARKER, NO_FACE_MARKER
from facial_identity.domain.errors import (
    MaxEnrollmentsReachedError,
    MultipleFacesDetectedError,
    NoEnrollmentsError,
    NoFaceDetectedError,
    SubjectAlreadyExistsError,
    SubjectInactiveError,
    SubjectLockedError,
    SubjectNotFoundError,
)
from facial_identity.domain.models import AuditAction, Decision, ReasonCode
from tests.conftest import FACE_ANA, FACE_ANA_2, FACE_LUIS


def _enrolled(service, external_id="CUST-1", name="Ana", face=FACE_ANA):
    subject = service.create_subject(external_id, name)
    service.enroll_face(subject.id, face)
    return subject


def test_no_permite_external_id_duplicado(service):
    service.create_subject("CUST-1", "Ana")
    with pytest.raises(SubjectAlreadyExistsError):
        service.create_subject("CUST-1", "Otra")


def test_verifica_match_con_el_mismo_rostro(service):
    ana = _enrolled(service)
    result = service.verify_face(ana.id, FACE_ANA)
    assert result.decision is Decision.MATCH
    assert result.reason_code is ReasonCode.SCORE_ABOVE_THRESHOLD


def test_verifica_contra_el_mejor_de_sus_rostros(service):
    ana = _enrolled(service)
    service.enroll_face(ana.id, FACE_ANA_2)
    assert service.verify_face(ana.id, FACE_ANA_2).decision is Decision.MATCH


def test_verifica_no_match_con_otra_persona(service):
    ana = _enrolled(service)
    assert service.verify_face(ana.id, FACE_LUIS).decision is Decision.NO_MATCH


def test_rechaza_registro_sin_rostro_o_con_varios(service):
    ana = service.create_subject("CUST-1", "Ana")
    with pytest.raises(NoFaceDetectedError):
        service.enroll_face(ana.id, NO_FACE_MARKER)
    with pytest.raises(MultipleFacesDetectedError):
        service.enroll_face(ana.id, MULTIPLE_FACES_MARKER)


def test_limita_cantidad_de_rostros_por_sujeto(service):
    ana = _enrolled(service)
    service.enroll_face(ana.id, FACE_ANA_2)
    with pytest.raises(MaxEnrollmentsReachedError):
        service.enroll_face(ana.id, b"\xff\xd8 tercera")


def test_verificar_sin_rostros_registrados_falla(service):
    ana = service.create_subject("CUST-1", "Ana")
    with pytest.raises(NoEnrollmentsError):
        service.verify_face(ana.id, FACE_ANA)


def test_sujeto_inactivo_no_verifica_ni_aparece_en_identificacion(service):
    ana = _enrolled(service)
    service.deactivate_subject(ana.id)
    with pytest.raises(SubjectInactiveError):
        service.verify_face(ana.id, FACE_ANA)
    assert service.identify_face(FACE_ANA).candidates == []


def test_reactivar_restaura_la_verificacion(service):
    ana = _enrolled(service)
    service.deactivate_subject(ana.id)
    service.reactivate_subject(ana.id)
    assert service.verify_face(ana.id, FACE_ANA).decision is Decision.MATCH


def test_identifica_al_sujeto_correcto_entre_varios(service):
    _enrolled(service)
    luis = _enrolled(service, "CUST-2", "Luis", FACE_LUIS)
    result = service.identify_face(FACE_LUIS)
    assert result.decision is Decision.MATCH
    assert [c.subject_id for c in result.candidates] == [luis.id]


def test_identificacion_sin_candidatos(service):
    _enrolled(service)
    result = service.identify_face(b"\xff\xd8 desconocido")
    assert result.decision is Decision.NO_MATCH
    assert result.reason_code is ReasonCode.NO_CANDIDATES


def test_bloquea_tras_fallos_y_desbloquea_con_el_tiempo(service, clock):
    ana = _enrolled(service)
    for _ in range(3):
        service.verify_face(ana.id, FACE_LUIS)
    with pytest.raises(SubjectLockedError):
        service.verify_face(ana.id, FACE_ANA)
    clock.advance(minutes=16)
    assert service.verify_face(ana.id, FACE_ANA).decision is Decision.MATCH


def test_match_reinicia_intentos_fallidos(service):
    ana = _enrolled(service)
    service.verify_face(ana.id, FACE_LUIS)
    service.verify_face(ana.id, FACE_ANA)
    assert service.get_subject(ana.id).failed_attempts == 0


def test_eliminar_borra_sujeto_y_rostros_del_motor(service):
    ana = _enrolled(service)
    service.delete_subject(ana.id)
    with pytest.raises(SubjectNotFoundError):
        service.get_subject(ana.id)
    assert service.identify_face(FACE_ANA).candidates == []


def test_audita_exitos_y_fallos_sin_guardar_la_imagen(service):
    ana = _enrolled(service)
    service.verify_face(ana.id, FACE_LUIS)
    with pytest.raises(NoFaceDetectedError):
        service.verify_face(ana.id, NO_FACE_MARKER)

    events = service.audit_events(ana.id)
    outcomes = [(e.action, e.outcome) for e in reversed(events)]
    assert outcomes == [
        (AuditAction.SUBJECT_CREATED, "OK"),
        (AuditAction.FACE_ENROLLED, "OK"),
        (AuditAction.FACE_VERIFIED, "NO_MATCH"),
        (AuditAction.FACE_VERIFIED, "NO_FACE"),
    ]
    assert all(len(e.image_sha256) == 64 for e in events if e.image_sha256)
