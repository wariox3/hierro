"""Configuración del servicio, leída de variables de entorno (y de `.env` en local)."""

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

_ESQUEMA_URL = "postgresql+asyncpg://"


class Settings(BaseSettings):
    """Variables de entorno del servicio. Están documentadas en `.env.example`."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # PostgreSQL
    database_url: str
    admin_database_url: str | None = None
    database_ssl: Literal["disable", "require", "verify-full"] = "require"
    database_ssl_root_cert: str | None = None
    database_pool_size: int = Field(default=5, ge=1)
    database_max_overflow: int = Field(default=5, ge=0)
    database_pool_timeout: float = Field(default=10.0, gt=0)
    database_pool_recycle: int = Field(default=1800, ge=60)
    database_statement_timeout_ms: int = Field(default=5000, ge=0)

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    redis_timeout: float = Field(default=0.5, gt=0)

    # Caché
    cache_ttl: int = Field(default=120, ge=1)
    http_cache_max_age: int = Field(default=60, ge=0)
    auth_cache_ttl: int = Field(default=300, ge=1)

    # Rate limiting por aplicación
    rate_limit_requests: int = Field(default=120, ge=1)
    rate_limit_window: int = Field(default=60, ge=1)

    # HTTP
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)
    docs_enabled: bool = True
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    @field_validator("database_url", "admin_database_url")
    @classmethod
    def _validar_url_postgres(cls, valor: str | None) -> str | None:
        if valor is None:
            return None
        if not valor.startswith(_ESQUEMA_URL):
            raise ValueError(f"debe empezar por {_ESQUEMA_URL}")
        if "sslmode=" in valor:
            raise ValueError("no incluyas sslmode en la URL; usa DATABASE_SSL")
        return valor

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _separar_origenes(cls, valor: object) -> object:
        if isinstance(valor, str):
            return [origen.strip() for origen in valor.split(",") if origen.strip()]
        return valor

    @property
    def url_admin(self) -> str:
        """URL del rol propietario (migraciones y gestión de API keys)."""
        return self.admin_database_url or self.database_url


@lru_cache
def get_settings() -> Settings:
    return Settings()
