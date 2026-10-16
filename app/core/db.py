"""Conexión a PostgreSQL con SQLAlchemy async + asyncpg, y la base declarativa de los modelos."""

import ssl
from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import Settings


class Base(DeclarativeBase):
    """Base común a todos los modelos de `app.models`."""


def argumentos_conexion(settings: Settings) -> dict[str, Any]:
    """Parámetros de asyncpg: TLS y ajustes de sesión.

    La conexión es directa a PostgreSQL (no a PgBouncer), así que la caché de
    sentencias preparadas de asyncpg puede quedar activa.
    """
    tls: ssl.SSLContext | str | bool
    if settings.database_ssl == "disable":
        tls = False
    elif settings.database_ssl == "require":
        tls = "require"
    else:
        tls = ssl.create_default_context(cafile=settings.database_ssl_root_cert)
    return {
        "ssl": tls,
        "server_settings": {
            "application_name": "hierro",
            "statement_timeout": str(settings.database_statement_timeout_ms),
        },
    }


def crear_engine(settings: Settings, url: str | None = None) -> AsyncEngine:
    return create_async_engine(
        url or settings.database_url,
        pool_pre_ping=True,
        pool_recycle=settings.database_pool_recycle,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_timeout=settings.database_pool_timeout,
        connect_args=argumentos_conexion(settings),
    )
