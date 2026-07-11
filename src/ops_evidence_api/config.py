from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables prefixed with ``OPS_``."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="OPS_",
        extra="ignore",
    )

    environment: Literal["development", "test", "production"] = "development"
    database_url: str = "postgresql+psycopg://ops_evidence:ops_evidence@localhost:5432/ops_evidence"
    fake_runner_enabled: bool = True
    fake_runner_poll_interval_seconds: float = Field(default=0.10, gt=0, le=10)
    fake_runner_delay_seconds: float = Field(default=0.15, ge=0, le=10)
    fixture_root: Path = Path("fixtures")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
