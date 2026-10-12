"""Prepara CompreFace para la demo sin pasar por su UI: crea (o reutiliza) un usuario admin,
una aplicación y un servicio de reconocimiento, y escribe su API key en `.env`.

Uso:  python scripts/bootstrap_compreface.py [--url http://localhost:8000]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import httpx

ADMIN_EMAIL = "demo@fis.local"
ADMIN_PASSWORD = "Demo12345!"
APP_NAME = "facial-identity-service"
SERVICE_NAME = "rostros"
ENV_FILE = Path(__file__).resolve().parents[1] / ".env"
ENV_EXAMPLE = ENV_FILE.with_name(".env.example")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://localhost:8000")
    args = parser.parse_args()

    with httpx.Client(base_url=args.url, timeout=30) as client:
        _register_admin(client)
        _login(client)
        app_id = _find_or_create(client, "/admin/apps", "/admin/app", {"name": APP_NAME})
        service = _find_or_create_service(client, app_id)

    _write_api_key(service["apiKey"])
    print(f"Listo. COMPREFACE_API_KEY={service['apiKey']} guardada en {ENV_FILE.name}")
    return 0


def _register_admin(client: httpx.Client) -> None:
    response = client.post(
        "/admin/user/register",
        json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD,
            "firstName": "Demo",
            "lastName": "FIS",
            "isAllowStatistics": False,
        },
    )
    if response.status_code not in (201, 400):  # 400: el usuario ya existe
        response.raise_for_status()


def _login(client: httpx.Client) -> None:
    # CompreFace usa un cliente OAuth fijo y deja la sesión en la cookie CFSESSION.
    client.post(
        "/admin/oauth/token",
        auth=("CommonClientId", "password"),
        data={"username": ADMIN_EMAIL, "password": ADMIN_PASSWORD, "grant_type": "password"},
    ).raise_for_status()


def _find_or_create(client: httpx.Client, list_path: str, create_path: str, body: dict) -> str:
    existing = [
        a for a in client.get(list_path).raise_for_status().json() if a["name"] == body["name"]
    ]
    if existing:
        return existing[0]["id"]
    return client.post(create_path, json=body).raise_for_status().json()["id"]


def _find_or_create_service(client: httpx.Client, app_id: str) -> dict:
    models = client.get(f"/admin/app/{app_id}/models").raise_for_status().json()
    for model in models:
        if model["name"] == SERVICE_NAME and model["type"] == "RECOGNITION":
            return model
    return (
        client.post(
            f"/admin/app/{app_id}/model", json={"name": SERVICE_NAME, "type": "RECOGNITION"}
        )
        .raise_for_status()
        .json()
    )


def _write_api_key(api_key: str) -> None:
    if not ENV_FILE.exists():
        ENV_FILE.write_text(ENV_EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
    content = ENV_FILE.read_text(encoding="utf-8")
    line = f"COMPREFACE_API_KEY={api_key}"
    if re.search(r"^COMPREFACE_API_KEY=.*$", content, flags=re.MULTILINE):
        content = re.sub(r"^COMPREFACE_API_KEY=.*$", line, content, flags=re.MULTILINE)
    else:
        content += f"\n{line}\n"
    ENV_FILE.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
