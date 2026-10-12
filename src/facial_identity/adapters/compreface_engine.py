"""Adaptador de CompreFace (REST /api/v1/recognition). Es el único módulo que conoce su API:
endpoints, x-api-key, formato de errores y forma de las respuestas."""

from __future__ import annotations

import contextlib
from typing import Any

import httpx

from facial_identity.domain.errors import (
    EngineError,
    EngineUnavailableError,
    MultipleFacesDetectedError,
    NoFaceDetectedError,
)
from facial_identity.domain.models import EngineMatch

# Código de error de CompreFace para "No face is found in the given image".
_NO_FACE_CODE = 28


class CompreFaceEngine:
    name = "compreface"

    def __init__(
        self,
        base_url: str,
        api_key: str,
        det_prob_threshold: float,
        timeout_seconds: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._det_prob_threshold = det_prob_threshold
        self._client = httpx.Client(
            base_url=f"{base_url.rstrip('/')}/api/v1/recognition",
            headers={"x-api-key": api_key},
            timeout=timeout_seconds,
            transport=transport,
        )

    def enroll(self, engine_subject: str, image: bytes) -> str:
        self._require_single_face(image)
        body = self._request(
            "POST",
            "/faces",
            params={"subject": engine_subject, "det_prob_threshold": self._det_prob_threshold},
            files=_image_file(image),
        )
        return str(body["image_id"])

    def verify(self, engine_face_id: str, image: bytes) -> float:
        body = self._request(
            "POST",
            f"/faces/{engine_face_id}/verify",
            params={"det_prob_threshold": self._det_prob_threshold},
            files=_image_file(image),
        )
        return float(_single_face(body)["similarity"])

    def identify(self, image: bytes, max_candidates: int) -> list[EngineMatch]:
        face = _single_face(self._recognize(image, max_candidates))
        return [EngineMatch(s["subject"], float(s["similarity"])) for s in face["subjects"]]

    def remove_subject(self, engine_subject: str) -> None:
        # El sujeto puede no existir en el motor (nunca registró rostros): borrar es idempotente.
        with contextlib.suppress(EngineError):
            self._request("DELETE", f"/subjects/{engine_subject}")

    def is_healthy(self) -> bool:
        try:
            self._request("GET", "/subjects/")
        except (EngineError, EngineUnavailableError):
            return False
        return True

    def _require_single_face(self, image: bytes) -> None:
        _single_face(self._recognize(image, prediction_count=1))

    def _recognize(self, image: bytes, prediction_count: int) -> dict[str, Any]:
        return self._request(
            "POST",
            "/recognize",
            params={
                "prediction_count": prediction_count,
                "det_prob_threshold": self._det_prob_threshold,
            },
            files=_image_file(image),
        )

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = self._client.request(method, path, **kwargs)
        except httpx.HTTPError as error:
            raise EngineUnavailableError(f"CompreFace no responde: {error}") from error
        if response.is_success:
            return response.json() if response.content else {}
        raise _translate_error(response)


def _image_file(image: bytes) -> dict[str, tuple[str, bytes, str]]:
    return {"file": ("image.jpg", image, "application/octet-stream")}


def _single_face(body: dict[str, Any]) -> dict[str, Any]:
    faces = body.get("result", [])
    if not faces:
        raise NoFaceDetectedError()
    if len(faces) > 1:
        raise MultipleFacesDetectedError()
    return faces[0]


def _translate_error(response: httpx.Response) -> Exception:
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    message = str(payload.get("message", response.text))
    if payload.get("code") == _NO_FACE_CODE or "no face" in message.lower():
        return NoFaceDetectedError()
    if response.status_code in (401, 403):
        return EngineUnavailableError("CompreFace rechazó la API key configurada")
    if response.status_code >= 500:
        return EngineUnavailableError(f"CompreFace falló ({response.status_code})")
    return EngineError(f"CompreFace respondió {response.status_code}: {message}")
