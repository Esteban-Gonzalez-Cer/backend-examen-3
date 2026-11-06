"""Application settings loaded from environment variables / `.env`."""

from functools import lru_cache
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Trayecta API"
    sii_base_url: str = "https://sii.celaya.tecnm.mx/api"
    sii_timeout_seconds: float = 10.0
    # Supabase session-pooler URL in production. The SQLite default only exists so the
    # project boots before the Supabase project is configured.
    database_url: str = "sqlite+aiosqlite:///./trayecta-local.db"
    session_ttl_minutes: int = 30
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]
    admin_control_numbers: Annotated[list[str], NoDecode] = []

    @field_validator("cors_origins", "admin_control_numbers", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @property
    def async_database_url(self) -> str:
        """Normalise the URL Supabase gives you (`postgresql://…`) to the asyncpg driver."""
        url = self.database_url.strip()
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://") :]
        if url.startswith("postgresql://"):
            url = "postgresql+asyncpg://" + url[len("postgresql://") :]
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()
