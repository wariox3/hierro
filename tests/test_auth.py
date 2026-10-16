import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.core.config import Settings
from app.core.redis_client import RedisSeguro
from app.utilidades.gestion_api_keys import ErrorGestion, crear_api_key, rotar_api_key
from tests.conftest import CrearCliente, Datos

URL = "/noticias/v1/lista"


async def test_sin_api_key_401(cliente: httpx.AsyncClient) -> None:
    respuesta = await cliente.get(URL)
    assert respuesta.status_code == 401
    assert respuesta.json()["error"]["codigo"] == "api_key_requerida"
    assert respuesta.headers["www-authenticate"] == "ApiKey"


async def test_api_key_invalida_401(cliente: httpx.AsyncClient, datos: Datos) -> None:
    await datos.api_key()
    respuesta = await cliente.get(URL, headers={"X-API-Key": "nk_inventada"})
    assert respuesta.status_code == 401
    assert respuesta.json()["error"]["codigo"] == "api_key_invalida"


async def test_api_key_demasiado_larga_401(cliente: httpx.AsyncClient) -> None:
    respuesta = await cliente.get(URL, headers={"X-API-Key": "x" * 1000})
    assert respuesta.status_code == 401


async def test_api_key_inactiva_403(cliente: httpx.AsyncClient, datos: Datos) -> None:
    _, key = await datos.api_key(inactiva=True)
    respuesta = await cliente.get(URL, headers={"X-API-Key": key})
    assert respuesta.status_code == 403
    assert respuesta.json()["error"]["codigo"] == "api_key_inactiva"


async def test_api_key_valida_200(cliente: httpx.AsyncClient, datos: Datos) -> None:
    _, key = await datos.api_key()
    respuesta = await cliente.get(URL, headers={"X-API-Key": key})
    assert respuesta.status_code == 200


async def test_validacion_se_cachea_en_redis(cliente: httpx.AsyncClient, datos: Datos) -> None:
    api_key, key = await datos.api_key()
    assert (await cliente.get(URL, headers={"X-API-Key": key})).status_code == 200
    # Desactivada por SQL: la caché de autenticación la sigue aceptando hasta su TTL.
    await datos.ejecutar(
        "UPDATE api_key SET estado_inactivo = true WHERE id = :id",
        id=api_key.id,
    )
    assert (await cliente.get(URL, headers={"X-API-Key": key})).status_code == 200


async def test_autenticacion_funciona_sin_redis(crear_cliente: CrearCliente, datos: Datos) -> None:
    _, key = await datos.api_key()
    async with crear_cliente(redis_url="redis://localhost:1/0") as cliente:
        assert (await cliente.get(URL, headers={"X-API-Key": key})).status_code == 200
        assert (await cliente.get(URL, headers={"X-API-Key": "nk_x"})).status_code == 401


async def test_crear_y_rotar_api_key(
    cliente: httpx.AsyncClient, db: AsyncEngine, settings: Settings
) -> None:
    sesiones = async_sessionmaker(db, expire_on_commit=False)
    redis = RedisSeguro.desde_url(settings.redis_url, settings.redis_timeout)
    try:
        api_key, key = await crear_api_key(sesiones, "cliente-nuevo")
        assert key.startswith("nk_")
        assert api_key.prefijo == key[:12]
        assert api_key.hash != key
        assert (await cliente.get(URL, headers={"X-API-Key": key})).status_code == 200

        _, nueva = await rotar_api_key(sesiones, redis, "cliente-nuevo")
        # La key anterior queda inválida al instante, aunque estuviera en caché.
        assert (await cliente.get(URL, headers={"X-API-Key": key})).status_code == 401
        assert (await cliente.get(URL, headers={"X-API-Key": nueva})).status_code == 200

        with pytest.raises(ErrorGestion, match="Ya existe"):
            await crear_api_key(sesiones, "cliente-nuevo")
        with pytest.raises(ErrorGestion, match="No existe"):
            await rotar_api_key(sesiones, redis, "otra")
    finally:
        await redis.cerrar()
