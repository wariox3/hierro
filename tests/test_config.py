"""Configuración de Redis: la URL lleva toda la conexión y el prefijo separa entornos."""

from typing import Any

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.redis_client import RedisSeguro


def _settings(**cambios: Any) -> Settings:
    return Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://u:p@localhost/x",
        **{"redis_key_prefix": "hierro:test", **cambios},
    )


async def test_opciones_tls_de_la_url_llegan_a_la_conexion() -> None:
    url = "rediss://default:x@redis.ejemplo.com:25061/0?ssl_ca_certs=/opt/hierro/certs/redis-ca.crt"
    redis = RedisSeguro.desde_url(_settings(redis_url=url).redis_url, 0.5, "hierro:test")
    try:
        opciones = redis._cliente.connection_pool.connection_kwargs
        assert opciones["host"] == "redis.ejemplo.com"
        assert opciones["port"] == 25061
        assert opciones["password"] == "x"
        assert opciones["ssl_ca_certs"] == "/opt/hierro/certs/redis-ca.crt"
    finally:
        await redis.cerrar()


@pytest.mark.parametrize("url", ["http://localhost:6379", "localhost:6379", "unix:///tmp/r.sock"])
def test_url_de_redis_invalida(url: str) -> None:
    with pytest.raises(ValidationError, match="redis://"):
        _settings(redis_url=url)


@pytest.mark.parametrize("prefijo", ["hierro:dev", "hierro:produccion", "hierro"])
def test_prefijo_de_redis_valido(prefijo: str) -> None:
    assert _settings(redis_key_prefix=prefijo).redis_key_prefix == prefijo


@pytest.mark.parametrize(
    "prefijo", ["", "hierro:", ":dev", "hierro dev", "hierro::dev", "hierro:*"]
)
def test_prefijo_de_redis_invalido(prefijo: str) -> None:
    with pytest.raises(ValidationError, match="hierro:dev"):
        _settings(redis_key_prefix=prefijo)


def test_prefijo_de_redis_obligatorio() -> None:
    with pytest.raises(ValidationError, match="redis_key_prefix"):
        Settings(_env_file=None, database_url="postgresql+asyncpg://u:p@localhost/x")
