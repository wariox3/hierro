"""Fixtures de integración contra PostgreSQL y Redis locales (sin Docker).

Variables (en el entorno o en `.env`):
  DATABASE_URL    sus credenciales se usan para crear la base `<nombre>_test` (si no
                  existe). La base de DATABASE_URL no se toca; la de tests se borra y
                  se migra de nuevo en cada corrida.
  TEST_REDIS_URL  base de Redis para tests (por defecto la 15): se vacía en cada test.
"""

import asyncio
import os
import subprocess
import sys
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic_settings import BaseSettings, SettingsConfigDict
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine as crear_engine_async

from app.core.api_keys import generar_api_key
from app.core.config import Settings
from app.main import create_app
from app.models import ApiKey, Noticia

RAIZ = Path(__file__).resolve().parents[1]

CrearCliente = Callable[..., AbstractAsyncContextManager[httpx.AsyncClient]]


class ConfigTests(BaseSettings):
    model_config = SettingsConfigDict(env_file=RAIZ / ".env", extra="ignore")

    database_url: str
    test_redis_url: str = "redis://localhost:6379/15"

    @property
    def test_database_url(self) -> str:
        """La URL de DATABASE_URL apuntando a la base `<nombre>_test`."""
        url = make_url(self.database_url)
        return url.set(database=f"{url.database}_test").render_as_string(hide_password=False)


@pytest.fixture(scope="session")
def config_tests() -> ConfigTests:
    return ConfigTests()


async def _preparar_base_tests(url_principal: str, url_tests: str) -> None:
    """Crea la base de tests si no existe y deja su esquema vacío."""
    nombre = make_url(url_tests).database or ""
    principal = crear_engine_async(
        url_principal, connect_args={"ssl": False}, isolation_level="AUTOCOMMIT"
    )
    async with principal.connect() as conexion:
        existe = await conexion.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :nombre"), {"nombre": nombre}
        )
        if not existe:
            identificador = '"' + nombre.replace('"', '""') + '"'
            await conexion.execute(text(f"CREATE DATABASE {identificador}"))
    await principal.dispose()

    tests = crear_engine_async(url_tests, connect_args={"ssl": False})
    async with tests.begin() as conexion:
        await conexion.execute(text("DROP SCHEMA public CASCADE"))
        await conexion.execute(text("CREATE SCHEMA public"))
    await tests.dispose()


@pytest.fixture(scope="session")
def esquema(config_tests: ConfigTests) -> None:
    """Base de tests vacía + `alembic upgrade head`, una vez por corrida."""
    url = config_tests.test_database_url
    asyncio.run(_preparar_base_tests(config_tests.database_url, url))
    entorno = {
        **os.environ,
        "DATABASE_URL": url,
        "ADMIN_DATABASE_URL": url,
        "DATABASE_SSL": "disable",
    }
    resultado = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=RAIZ,
        env=entorno,
        capture_output=True,
        text=True,
        check=False,
    )
    if resultado.returncode != 0:
        pytest.exit(f"alembic upgrade head falló:\n{resultado.stderr}")


@pytest.fixture
def settings(config_tests: ConfigTests, esquema: None) -> Settings:
    return Settings(
        _env_file=None,
        database_url=config_tests.test_database_url,
        database_ssl="disable",
        redis_url=config_tests.test_redis_url,
        redis_key_prefix="hierro:test",
        rate_limit_requests=1000,
    )


@pytest.fixture
async def db(settings: Settings) -> AsyncIterator[AsyncEngine]:
    engine = crear_engine_async(settings.database_url, connect_args={"ssl": False})
    async with engine.begin() as conexion:
        await conexion.execute(text("TRUNCATE noticia, api_key RESTART IDENTITY"))
    yield engine
    await engine.dispose()


@pytest.fixture
async def redis_tests(settings: Settings) -> AsyncIterator[Redis]:
    cliente = Redis.from_url(settings.redis_url)
    await cliente.flushdb()
    yield cliente
    await cliente.aclose()


class Datos:
    """Inserta datos de prueba como lo haría un editor: directamente en la base."""

    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine
        self._sesiones = async_sessionmaker(engine, expire_on_commit=False)

    async def _guardar[T](self, objeto: T) -> T:
        sesion: AsyncSession
        async with self._sesiones() as sesion, sesion.begin():
            sesion.add(objeto)
        return objeto

    async def api_key(
        self, nombre: str = "cliente", *, inactiva: bool = False
    ) -> tuple[ApiKey, str]:
        """Guarda una API key y devuelve el registro y la key en claro."""
        generada = generar_api_key()
        api_key = await self._guardar(
            ApiKey(
                nombre=nombre,
                hash=generada.hash,
                prefijo=generada.prefijo,
                estado_inactivo=inactiva,
            )
        )
        return api_key, generada.key

    async def noticia(
        self,
        titulo: str = "Noticia",
        *,
        fecha_publicacion: datetime | None = None,
        inactiva: bool = False,
        contenido: str | None = "<p>Contenido</p>",
        url_imagen: str | None = None,
        fecha_actualizacion: datetime | None = None,
    ) -> Noticia:
        noticia = Noticia(
            titulo=titulo,
            contenido=contenido,
            url_imagen=url_imagen,
            fecha_publicacion=fecha_publicacion or datetime.now(UTC) - timedelta(hours=1),
            estado_inactivo=inactiva,
        )
        if fecha_actualizacion is not None:
            noticia.fecha_actualizacion = fecha_actualizacion
        return await self._guardar(noticia)

    async def ejecutar(self, sql: str, **parametros: Any) -> None:
        async with self.engine.begin() as conexion:
            await conexion.execute(text(sql), parametros)


@pytest.fixture
def datos(db: AsyncEngine) -> Datos:
    return Datos(db)


@pytest.fixture
def crear_cliente(settings: Settings, db: AsyncEngine, redis_tests: Redis) -> CrearCliente:
    """Cliente HTTP contra una app real; acepta cambios de configuración."""

    @asynccontextmanager
    async def _crear(**cambios: Any) -> AsyncIterator[httpx.AsyncClient]:
        app = create_app(settings.model_copy(update=cambios))
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as cliente,
        ):
            yield cliente

    return _crear


@pytest.fixture
async def cliente(crear_cliente: CrearCliente) -> AsyncIterator[httpx.AsyncClient]:
    async with crear_cliente() as cliente:
        yield cliente
