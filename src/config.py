"""Centralized configuration loaded from environment variables.

Configuration is intentionally minimal so the prototype can be run with
zero setup (sensible defaults) but still ported to a Gen3/AWS deployment
by overriding env vars.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings sourced from env vars or a local .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="VLC_",
        extra="ignore",
        case_sensitive=False,
    )

    db_path: Path = Field(default=Path("./data/virtuallab.db"))
    random_seed: int = Field(default=42)
    num_patients: int = Field(default=400)
    api_base_url: str = Field(default="http://localhost:8000")
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000)
    llm_provider: str = Field(default="")
    llm_api_key: str = Field(default="")

    @property
    def db_uri(self) -> str:
        return f"sqlite:///{self.db_path}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
