"""Motor simulado. Sirve para los tests y para demostrar que la API, las reglas y la auditoría
no dependen de CompreFace. Considera "el mismo rostro" a dos imágenes idénticas byte a byte."""

from __future__ import annotations

import hashlib
import uuid

from facial_identity.domain.errors import MultipleFacesDetectedError, NoFaceDetectedError
from facial_identity.domain.models import EngineMatch

# Marcadores para simular imágenes problemáticas en pruebas.
NO_FACE_MARKER = b"NOFACE"
MULTIPLE_FACES_MARKER = b"MULTIFACE"


class FakeFaceEngine:
    name = "fake"

    def __init__(self) -> None:
        self._faces: dict[str, tuple[str, str]] = {}

    def enroll(self, engine_subject: str, image: bytes) -> str:
        fingerprint = _fingerprint(image)
        face_id = str(uuid.uuid4())
        self._faces[face_id] = (engine_subject, fingerprint)
        return face_id

    def verify(self, engine_face_id: str, image: bytes) -> float:
        fingerprint = _fingerprint(image)
        face = self._faces.get(engine_face_id)
        if face is None:
            return 0.0
        return 1.0 if face[1] == fingerprint else 0.1

    def identify(self, image: bytes, max_candidates: int) -> list[EngineMatch]:
        fingerprint = _fingerprint(image)
        best: dict[str, float] = {}
        for subject, enrolled in self._faces.values():
            score = 1.0 if enrolled == fingerprint else 0.1
            best[subject] = max(score, best.get(subject, 0.0))
        ranked = sorted(best.items(), key=lambda item: item[1], reverse=True)
        return [EngineMatch(subject, score) for subject, score in ranked[:max_candidates]]

    def remove_subject(self, engine_subject: str) -> None:
        self._faces = {k: v for k, v in self._faces.items() if v[0] != engine_subject}

    def is_healthy(self) -> bool:
        return True


def _fingerprint(image: bytes) -> str:
    if not image or image.startswith(NO_FACE_MARKER):
        raise NoFaceDetectedError()
    if image.startswith(MULTIPLE_FACES_MARKER):
        raise MultipleFacesDetectedError()
    return hashlib.sha256(image).hexdigest()
