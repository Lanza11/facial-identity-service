from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    fis_engine: Literal["compreface", "fake"] = "compreface"
    fis_api_key: str = "demo-key"
    fis_data_dir: Path = Path("data")

    fis_match_threshold: float = 0.90
    fis_inconclusive_threshold: float = 0.80
    fis_max_enrollments: int = 3
    fis_max_failed_attempts: int = 5
    fis_lockout_minutes: int = 15
    fis_identify_candidates: int = 3
    fis_max_image_bytes: int = 5 * 1024 * 1024

    compreface_url: str = "http://localhost:8000"
    compreface_api_key: str = ""
    compreface_det_prob_threshold: float = 0.8

    @property
    def db_path(self) -> Path:
        # Una base por motor: los rostros registrados en un motor no existen en otro.
        return self.fis_data_dir / f"fis-{self.fis_engine}.db"
