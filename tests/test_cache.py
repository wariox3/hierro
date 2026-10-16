"""Caché de respuestas en Redis, ETag/304 y funcionamiento sin Redis."""

import logging

import httpx
import pytest
from redis.asyncio import Redis

from app.core.cache import etag_coincide
from tests.conftest import CrearCliente, Datos


async def test_listado_se_cachea_hasta_el_ttl(
    cliente: httpx.AsyncClient, datos: Datos, redis_tests: Redis
) -> None:
    _, key = await datos.api_key()
    primera = await datos.noticia("Primera")
    antes = await cliente.get("/v1/noticias", headers={"X-API-Key": key})

    # Inserción manual por SQL: la API no se entera hasta que vence la caché.
    await datos.noticia("Segunda")
    cacheada = await cliente.get("/v1/noticias", headers={"X-API-Key": key})
    assert cacheada.content == antes.content
    assert [n["id"] for n in cacheada.json()["datos"]] == [primera.id]

    claves = [clave.decode() async for clave in redis_tests.scan_iter("news:v1:noticias:*")]
    assert len(claves) == 1
    assert 0 < await redis_tests.ttl(claves[0]) <= 120

    await redis_tests.delete(*claves)
    actualizada = await cliente.get("/v1/noticias", headers={"X-API-Key": key})
    assert len(actualizada.json()["datos"]) == 2


async def test_la_cache_se_comparte_entre_keys_y_separa_parametros(
    cliente: httpx.AsyncClient, datos: Datos, redis_tests: Redis
) -> None:
    _, key_a = await datos.api_key("a")
    _, key_b = await datos.api_key("b")
    await datos.noticia("Primera")
    await datos.noticia("Segunda")

    a = await cliente.get("/v1/noticias", headers={"X-API-Key": key_a})
    b = await cliente.get("/v1/noticias", headers={"X-API-Key": key_b})
    a_limit = await cliente.get("/v1/noticias", params={"limit": 1}, headers={"X-API-Key": key_a})

    # Todas las keys ven las mismas noticias: comparten la entrada de caché.
    assert a.content == b.content
    assert a.headers["etag"] == b.headers["etag"]
    assert len(a_limit.json()["datos"]) == 1
    claves = {clave async for clave in redis_tests.scan_iter("news:v1:noticias:*")}
    assert len(claves) == 2


async def test_detalle_se_cachea(cliente: httpx.AsyncClient, datos: Datos) -> None:
    _, key = await datos.api_key()
    noticia = await datos.noticia("Original")
    url = f"/v1/noticias/{noticia.id}"
    assert (await cliente.get(url, headers={"X-API-Key": key})).json()["titulo"] == "Original"
    await datos.ejecutar(
        "UPDATE noticia SET titulo = 'Editada' WHERE id = :id",
        id=noticia.id,
    )
    assert (await cliente.get(url, headers={"X-API-Key": key})).json()["titulo"] == "Original"


async def test_404_no_se_cachea(cliente: httpx.AsyncClient, datos: Datos) -> None:
    _, key = await datos.api_key()
    noticia = await datos.noticia()
    await datos.ejecutar(
        "UPDATE noticia SET estado_inactivo = true WHERE id = :id",
        id=noticia.id,
    )
    url = f"/v1/noticias/{noticia.id}"
    assert (await cliente.get(url, headers={"X-API-Key": key})).status_code == 404
    await datos.ejecutar(
        "UPDATE noticia SET estado_inactivo = false WHERE id = :id",
        id=noticia.id,
    )
    assert (await cliente.get(url, headers={"X-API-Key": key})).status_code == 200


@pytest.mark.parametrize("ruta", ["/v1/noticias", "/v1/noticias/{id}"])
async def test_etag_y_304(cliente: httpx.AsyncClient, datos: Datos, ruta: str) -> None:
    _, key = await datos.api_key()
    noticia = await datos.noticia()
    url = ruta.format(id=noticia.id)

    respuesta = await cliente.get(url, headers={"X-API-Key": key})
    etag = respuesta.headers["etag"]
    assert etag.startswith('"')
    assert respuesta.headers["cache-control"] == "private, max-age=60"
    assert respuesta.headers["vary"] == "X-API-Key"

    no_modificada = await cliente.get(url, headers={"X-API-Key": key, "If-None-Match": etag})
    assert no_modificada.status_code == 304
    assert no_modificada.content == b""
    assert no_modificada.headers["etag"] == etag

    # Nginx debilita el ETag al comprimir con gzip: también debe coincidir.
    debil = await cliente.get(url, headers={"X-API-Key": key, "If-None-Match": f"W/{etag}"})
    assert debil.status_code == 304

    distinta = await cliente.get(url, headers={"X-API-Key": key, "If-None-Match": '"otro"'})
    assert distinta.status_code == 200


def test_comparacion_de_etags() -> None:
    assert etag_coincide('"a", "b"', '"b"')
    assert etag_coincide("*", '"b"')
    assert etag_coincide('W/"b"', '"b"')
    assert not etag_coincide(None, '"b"')
    assert not etag_coincide('"a"', '"b"')


async def test_sin_redis_la_api_funciona_y_registra_el_error(
    crear_cliente: CrearCliente, datos: Datos, caplog: pytest.LogCaptureFixture
) -> None:
    _, key = await datos.api_key()
    noticia = await datos.noticia()
    caplog.set_level(logging.WARNING, logger="app.redis")
    async with crear_cliente(redis_url="redis://localhost:1/0") as cliente:
        listado = await cliente.get("/v1/noticias", headers={"X-API-Key": key})
        detalle = await cliente.get(f"/v1/noticias/{noticia.id}", headers={"X-API-Key": key})
        etag = detalle.headers["etag"]
        no_modificada = await cliente.get(
            f"/v1/noticias/{noticia.id}",
            headers={"X-API-Key": key, "If-None-Match": etag},
        )
    assert listado.status_code == 200
    assert len(listado.json()["datos"]) == 1
    assert detalle.status_code == 200
    assert no_modificada.status_code == 304
    avisos = [r for r in caplog.records if r.getMessage() == "redis_no_disponible"]
    assert avisos
    assert avisos[0].levelno == logging.WARNING
