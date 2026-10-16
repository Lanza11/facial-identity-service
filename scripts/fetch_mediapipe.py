"""Descarga MediaPipe Face Landmarker (librería web + WASM + modelo) a demo/vendor/mediapipe para
que la demo funcione sin internet. Los archivos pesan ~40 MB y no se versionan en git.

Uso:  python scripts/fetch_mediapipe.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import httpx

VERSION = "1.0.1"
PACKAGE = f"https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@{VERSION}"
MODEL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/"
    "float16/1/face_landmarker.task"
)
TARGET = Path(__file__).resolve().parents[1] / "demo" / "vendor" / "mediapipe"

FILES = {
    "vision_bundle.mjs": f"{PACKAGE}/vision_bundle.mjs",
    "wasm/vision_wasm_internal.js": f"{PACKAGE}/wasm/vision_wasm_internal.js",
    "wasm/vision_wasm_internal.wasm": f"{PACKAGE}/wasm/vision_wasm_internal.wasm",
    "wasm/vision_wasm_nosimd_internal.js": f"{PACKAGE}/wasm/vision_wasm_nosimd_internal.js",
    "wasm/vision_wasm_nosimd_internal.wasm": f"{PACKAGE}/wasm/vision_wasm_nosimd_internal.wasm",
    "face_landmarker.task": MODEL,
}


def main() -> int:
    with httpx.Client(timeout=120, follow_redirects=True) as client:
        for name, url in FILES.items():
            destination = TARGET / name
            if destination.exists() and destination.stat().st_size > 0:
                print(f"ya existe  {name}")
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            response = client.get(url)
            response.raise_for_status()
            destination.write_bytes(response.content)
            print(f"descargado {name} ({len(response.content) / 1_048_576:.1f} MB)")
    print(f"MediaPipe {VERSION} listo en {TARGET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
