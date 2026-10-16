"""Regla de visibilidad, detalle, paginación por cursor y filtros."""

import base64
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from tests.conftest import Datos

AHORA = datetime.now(UTC)


def _ids(respuesta: httpx.Response) -> list[int]:
    assert respuesta.status_code == 200, respuesta.text
    return [noticia["id"] for noticia in respuesta.json()["datos"]]


# --- Visibilidad ---------------------------------------------------------------


async def test_regla_de_visibilidad(cliente: httpx.AsyncClient, datos: Datos) -> None:
    _, key_a = await datos.api_key("a")
    _, key_b = await datos.api_key("b")
    visible = await datos.noticia("Visible")
    despublicada = await datos.noticia("Despublicada", inactiva=True)
    programada = await datos.noticia("Programada", fecha_publicacion=AHORA + timedelta(days=1))

    vistas_a = set(_ids(await cliente.get("/v1/noticias", headers={"X-API-Key": key_a})))
    vistas_b = set(_ids(await cliente.get("/v1/noticias", headers={"X-API-Key": key_b})))

    esperadas = {visible.id}
    assert vistas_a == esperadas
    # Todas las API keys ven las mismas noticias.
    assert vistas_b == esperadas

    for oculta in (despublicada, programada):
        respuesta = await cliente.get(f"/v1/noticias/{oculta.id}", headers={"X-API-Key": key_a})
        assert respuesta.status_code == 404, oculta.titulo


async def test_detalle_incluye_contenido(cliente: httpx.AsyncClient, datos: Datos) -> None:
    _, key = await datos.api_key()
    noticia = await datos.noticia(
        "Detalle",
        contenido="<p>Hola</p>",
        url_imagen="https://cdn.ejemplo.com/a.jpg",
    )
    respuesta = await cliente.get(f"/v1/noticias/{noticia.id}", headers={"X-API-Key": key})
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["contenido"] == "<p>Hola</p>"
    assert cuerpo["titulo"] == "Detalle"
    assert cuerpo["url_imagen"] == "https://cdn.ejemplo.com/a.jpg"
    assert datetime.fromisoformat(cuerpo["fecha_publicacion"]).tzinfo is not None


async def test_listado_incluye_contenido_sanitizado(
    cliente: httpx.AsyncClient, datos: Datos
) -> None:
    _, key = await datos.api_key()
    await datos.noticia(contenido="<p>Hola</p><script>alert(1)</script>")
    noticia = (await cliente.get("/v1/noticias", headers={"X-API-Key": key})).json()["datos"][0]
    assert noticia["contenido"] == "<p>Hola</p>"
    assert set(noticia) == {
        "id",
        "titulo",
        "contenido",
        "url_imagen",
        "fecha_publicacion",
        "fecha_actualizacion",
    }


@pytest.mark.parametrize("ruta", ["/v1/noticias/999999", "/v1/noticias/2147483647"])
async def test_detalle_inexistente_404(cliente: httpx.AsyncClient, datos: Datos, ruta: str) -> None:
    _, key = await datos.api_key()
    respuesta = await cliente.get(ruta, headers={"X-API-Key": key})
    assert respuesta.status_code == 404
    assert respuesta.json()["error"]["codigo"] == "noticia_no_encontrada"


@pytest.mark.parametrize("ruta", ["/v1/noticias/0", "/v1/noticias/abc", "/v1/noticias/2147483648"])
async def test_detalle_id_invalido_422(cliente: httpx.AsyncClient, datos: Datos, ruta: str) -> None:
    _, key = await datos.api_key()
    respuesta = await cliente.get(ruta, headers={"X-API-Key": key})
    assert respuesta.status_code == 422
    assert respuesta.json()["error"]["codigo"] == "parametros_invalidos"


# --- Paginación por cursor -----------------------------------------------------


async def test_paginacion_recorre_todo_sin_duplicados(
    cliente: httpx.AsyncClient, datos: Datos
) -> None:
    _, key = await datos.api_key()
    empate = AHORA - timedelta(hours=3)
    creadas = [
        await datos.noticia(f"N{i}", fecha_publicacion=AHORA - timedelta(hours=i))
        for i in range(1, 6)
    ]
    # Dos noticias con la misma fecha: el id desempata.
    creadas += [await datos.noticia(f"E{i}", fecha_publicacion=empate) for i in range(2)]
    esperado = [
        n.id for n in sorted(creadas, key=lambda n: (n.fecha_publicacion, n.id), reverse=True)
    ]

    vistos: list[int] = []
    cursor: str | None = None
    paginas = 0
    while True:
        parametros: dict[str, str | int] = {"limit": 2}
        if cursor:
            parametros["cursor"] = cursor
        respuesta = await cliente.get("/v1/noticias", params=parametros, headers={"X-API-Key": key})
        cuerpo = respuesta.json()
        vistos += _ids(respuesta)
        paginas += 1
        cursor = cuerpo["siguiente_cursor"]
        if cursor is None:
            break

    assert vistos == esperado
    assert paginas == 4


async def test_limite_por_defecto_20(cliente: httpx.AsyncClient, datos: Datos) -> None:
    _, key = await datos.api_key()
    for i in range(21):
        await datos.noticia(f"N{i}", fecha_publicacion=AHORA - timedelta(minutes=i + 1))
    cuerpo = (await cliente.get("/v1/noticias", headers={"X-API-Key": key})).json()
    assert len(cuerpo["datos"]) == 20
    assert cuerpo["siguiente_cursor"] is not None


async def test_ultima_pagina_exacta_no_tiene_cursor(
    cliente: httpx.AsyncClient, datos: Datos
) -> None:
    _, key = await datos.api_key()
    for i in range(2):
        await datos.noticia(f"N{i}")
    cuerpo = (
        await cliente.get("/v1/noticias", params={"limit": 2}, headers={"X-API-Key": key})
    ).json()
    assert len(cuerpo["datos"]) == 2
    assert cuerpo["siguiente_cursor"] is None


@pytest.mark.parametrize("limite", [0, 51, -1])
async def test_limite_fuera_de_rango_422(
    cliente: httpx.AsyncClient, datos: Datos, limite: int
) -> None:
    _, key = await datos.api_key()
    respuesta = await cliente.get(
        "/v1/noticias", params={"limit": limite}, headers={"X-API-Key": key}
    )
    assert respuesta.status_code == 422


@pytest.mark.parametrize(
    "cursor",
    [
        "no-es-base64!!",
        base64.urlsafe_b64encode(b"[]").decode(),
        base64.urlsafe_b64encode(b'{"f": "ayer", "i": 1}').decode(),
        base64.urlsafe_b64encode(b'{"f": "2026-01-01T00:00:00", "i": 1}').decode(),
        base64.urlsafe_b64encode(b'{"f": "2026-01-01T00:00:00+00:00", "i": "1"}').decode(),
    ],
)
async def test_cursor_invalido_400(cliente: httpx.AsyncClient, datos: Datos, cursor: str) -> None:
    _, key = await datos.api_key()
    respuesta = await cliente.get(
        "/v1/noticias", params={"cursor": cursor}, headers={"X-API-Key": key}
    )
    assert respuesta.status_code == 400
    assert respuesta.json()["error"]["codigo"] == "cursor_invalido"


# --- Filtros -------------------------------------------------------------------


async def test_filtro_updated_since(cliente: httpx.AsyncClient, datos: Datos) -> None:
    _, key = await datos.api_key()
    hace_10_dias = AHORA - timedelta(days=10)
    antigua = await datos.noticia(
        "Antigua", fecha_publicacion=hace_10_dias, fecha_actualizacion=hace_10_dias
    )
    editada = await datos.noticia(
        "Editada", fecha_publicacion=hace_10_dias, fecha_actualizacion=hace_10_dias
    )
    await datos.ejecutar(
        "UPDATE noticia SET titulo = 'Editada hoy' WHERE id = :id",
        id=editada.id,
    )
    # Cargada hace días como programada; se publicó hace una hora sin que nadie la tocara.
    programada = await datos.noticia(
        "Programada",
        fecha_publicacion=AHORA - timedelta(hours=1),
        fecha_actualizacion=hace_10_dias,
    )

    desde = (AHORA - timedelta(days=2)).isoformat()
    respuesta = await cliente.get(
        "/v1/noticias", params={"updated_since": desde}, headers={"X-API-Key": key}
    )
    assert set(_ids(respuesta)) == {editada.id, programada.id}
    assert antigua.id not in _ids(respuesta)

    # Con otra zona horaria significa el mismo instante.
    desde_otra_zona = (AHORA - timedelta(days=2)).astimezone().isoformat()
    respuesta = await cliente.get(
        "/v1/noticias", params={"updated_since": desde_otra_zona}, headers={"X-API-Key": key}
    )
    assert set(_ids(respuesta)) == {editada.id, programada.id}


async def test_updated_since_sin_zona_horaria_422(cliente: httpx.AsyncClient, datos: Datos) -> None:
    _, key = await datos.api_key()
    respuesta = await cliente.get(
        "/v1/noticias",
        params={"updated_since": "2026-01-01T00:00:00"},
        headers={"X-API-Key": key},
    )
    assert respuesta.status_code == 422
