"""Entorno de Alembic en modo async.

Usa el rol propietario del esquema (ADMIN_DATABASE_URL), distinto de los roles
api_noticias y editor_noticias.
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import Settings
from app.core.db import argumentos_conexion
from app.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _ejecutar(conexion: Connection) -> None:
    context.configure(connection=conexion, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def _migrar_online() -> None:
    settings = Settings()
    engine = create_async_engine(
        settings.url_admin, poolclass=NullPool, connect_args=argumentos_conexion(settings)
    )
    async with engine.connect() as conexion:
        await conexion.run_sync(_ejecutar)
    await engine.dispose()


if context.is_offline_mode():
    raise SystemExit("El modo offline no está soportado: ejecuta las migraciones contra la base.")

asyncio.run(_migrar_online())
