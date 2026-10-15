FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    FIS_DATA_DIR=/data

WORKDIR /app

COPY pyproject.toml ./
RUN pip install --no-cache-dir \
    "fastapi>=0.115,<1" "uvicorn[standard]>=0.30,<1" "httpx>=0.27,<1" \
    "pydantic>=2.8,<3" "pydantic-settings>=2.4,<3" "python-multipart>=0.0.9"

COPY src ./src
COPY demo ./demo
# MediaPipe para la prueba de vida de la demo: reutiliza demo/vendor si ya está, si no lo descarga.
COPY scripts/fetch_mediapipe.py ./scripts/
RUN python scripts/fetch_mediapipe.py

RUN useradd --create-home fis && mkdir -p /data && chown fis /data
USER fis

EXPOSE 8080
CMD ["uvicorn", "facial_identity.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080"]
