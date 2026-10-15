from tests.conftest import FACE_ANA, FACE_LUIS


def _image(content: bytes):
    return {"image": ("foto.jpg", content, "image/jpeg")}


def _create(client, external_id="CUST-1", name="Ana", consent=True):
    response = client.post("/v1/subjects", json={"externalId": external_id, "displayName": name})
    assert response.status_code == 201
    subject_id = response.json()["subjectId"]
    if consent:
        consent_body = {"textVersion": "biometria-v1", "channel": "sede"}
        assert (
            client.post(f"/v1/subjects/{subject_id}/consents", json=consent_body).status_code == 201
        )
    return subject_id


def test_health_es_publico(client):
    response = client.get("/health", headers={"x-api-key": ""})
    assert response.json() == {"status": "UP", "engine": "fake", "engineStatus": "UP"}


def test_rechaza_peticiones_sin_api_key(client):
    response = client.get("/v1/subjects", headers={"x-api-key": "otra"})
    assert response.status_code == 401
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["slug"] == "UNAUTHORIZED"


def test_flujo_completo_registro_verificacion_identificacion(client):
    subject_id = _create(client)
    enrolled = client.post(f"/v1/subjects/{subject_id}/enrollments", files=_image(FACE_ANA))
    assert enrolled.status_code == 201

    verification = client.post(
        f"/v1/subjects/{subject_id}/verifications", files=_image(FACE_ANA)
    ).json()
    assert verification["decision"] == "MATCH"
    assert set(verification) == {"verificationId", "subjectId", "decision", "score", "reasonCode"}

    identification = client.post("/v1/identifications", files=_image(FACE_ANA)).json()
    assert identification["candidates"][0]["externalId"] == "CUST-1"


def test_errores_de_negocio_como_problem_details(client):
    subject_id = _create(client)
    client.post(f"/v1/subjects/{subject_id}/deactivate")
    response = client.post(f"/v1/subjects/{subject_id}/verifications", files=_image(FACE_LUIS))
    assert response.status_code == 409
    assert response.json()["slug"] == "SUBJECT_INACTIVE"


def test_rechaza_archivos_que_no_son_imagen(client):
    subject_id = _create(client)
    response = client.post(
        f"/v1/subjects/{subject_id}/enrollments",
        files={"image": ("notas.txt", b"hola", "text/plain")},
    )
    assert response.status_code == 422
    assert response.json()["slug"] == "INVALID_IMAGE"


def test_eliminar_y_consultar_auditoria(client):
    subject_id = _create(client)
    assert client.delete(f"/v1/subjects/{subject_id}").status_code == 204
    assert client.get("/v1/subjects").json() == []
    audit = client.get("/v1/audit", params={"subjectId": subject_id}).json()
    assert [e["action"] for e in audit] == ["SUBJECT_DELETED", "CONSENT_GRANTED", "SUBJECT_CREATED"]


def test_errores_de_validacion_como_problem_details(client):
    response = client.post("/v1/subjects", json={"externalId": ""})
    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["slug"] == "VALIDATION_ERROR"


def test_registro_sin_consentimiento_devuelve_problema(client):
    subject_id = _create(client, consent=False)
    assert client.get("/v1/subjects").json()[0]["consentedAt"] is None
    response = client.post(f"/v1/subjects/{subject_id}/enrollments", files=_image(FACE_ANA))
    assert response.status_code == 409
    assert response.json()["slug"] == "CONSENT_REQUIRED"


def test_recibe_el_resultado_de_la_prueba_de_vida(client):
    subject_id = _create(client)
    response = client.post(
        f"/v1/subjects/{subject_id}/enrollments",
        files=_image(FACE_ANA),
        data={"liveness": "PASSED"},
    )
    assert response.status_code == 201
    audit = client.get("/v1/audit", params={"subjectId": subject_id}).json()
    assert audit[0]["detail"] == "liveness=PASSED"
