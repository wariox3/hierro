"""Listado de noticias: visibilidad, orden, tope de 10 y contenido."""

from datetime import UTC, datetime, timedelta

import httpx

from tests.conftest import Datos

URL = "/noticias/v1/lista"
AHORA = datetime.now(UTC)


def _ids(respuesta: httpx.Response) -> list[int]:
    assert respuesta.status_code == 200, respuesta.text
    return [noticia["id"] for noticia in respuesta.json()["datos"]]


# --- Visibilidad ---------------------------------------------------------------


async def test_solo_se_ocultan_las_inactivas(cliente: httpx.AsyncClient, datos: Datos) -> None:
    _, key_a = await datos.api_key("a")
    _, key_b = await datos.api_key("b")
    visible = await datos.noticia("Visible")
    await datos.noticia("Despublicada", inactiva=True)
    # La fecha de publicación no filtra: las programadas se muestran ya.
    programada = await datos.noticia("Programada", fecha_publicacion=AHORA + timedelta(days=1))

    vistas_a = set(_ids(await cliente.get(URL, headers={"X-API-Key": key_a})))
    vistas_b = set(_ids(await cliente.get(URL, headers={"X-API-Key": key_b})))

    esperadas = {visible.id, programada.id}
    assert vistas_a == esperadas
    # Todas las API keys ven las mismas noticias.
    assert vistas_b == esperadas


async def test_sin_noticias_devuelve_lista_vacia(cliente: httpx.AsyncClient, datos: Datos) -> None:
    _, key = await datos.api_key()
    await datos.noticia("Despublicada", inactiva=True)
    respuesta = await cliente.get(URL, headers={"X-API-Key": key})
    assert respuesta.status_code == 200
    assert respuesta.json() == {"datos": []}


# --- Orden y tope --------------------------------------------------------------


async def test_ordenadas_por_fecha_descendente_con_desempate_por_id(
    cliente: httpx.AsyncClient, datos: Datos
) -> None:
    _, key = await datos.api_key()
    empate = AHORA - timedelta(hours=3)
    creadas = [
        await datos.noticia(f"N{i}", fecha_publicacion=AHORA - timedelta(hours=i))
        for i in range(1, 5)
    ]
    # Dos noticias con la misma fecha: el id mayor va primero.
    creadas += [await datos.noticia(f"E{i}", fecha_publicacion=empate) for i in range(2)]
    esperado = [
        n.id for n in sorted(creadas, key=lambda n: (n.fecha_publicacion, n.id), reverse=True)
    ]

    assert _ids(await cliente.get(URL, headers={"X-API-Key": key})) == esperado


async def test_devuelve_como_maximo_las_10_mas_recientes(
    cliente: httpx.AsyncClient, datos: Datos
) -> None:
    _, key = await datos.api_key()
    creadas = [
        await datos.noticia(f"N{i}", fecha_publicacion=AHORA - timedelta(minutes=i + 1))
        for i in range(12)
    ]
    # Una inactiva más reciente que todas no ocupa lugar en las 10.
    await datos.noticia("Inactiva", fecha_publicacion=AHORA, inactiva=True)

    assert _ids(await cliente.get(URL, headers={"X-API-Key": key})) == [n.id for n in creadas[:10]]


async def test_ignora_parametros_de_paginacion_y_filtros(
    cliente: httpx.AsyncClient, datos: Datos
) -> None:
    _, key = await datos.api_key()
    for i in range(3):
        await datos.noticia(f"N{i}")
    sin_parametros = await cliente.get(URL, headers={"X-API-Key": key})
    con_parametros = await cliente.get(
        URL,
        params={"limit": 1, "cursor": "no-es-un-cursor", "updated_since": "ayer"},
        headers={"X-API-Key": key},
    )
    assert con_parametros.status_code == 200
    assert con_parametros.content == sin_parametros.content
    assert len(con_parametros.json()["datos"]) == 3


# --- Contenido -----------------------------------------------------------------


async def test_incluye_todos_los_campos_y_contenido_sanitizado(
    cliente: httpx.AsyncClient, datos: Datos
) -> None:
    _, key = await datos.api_key()
    await datos.noticia(
        "Con contenido",
        contenido="<p>Hola</p><script>alert(1)</script>",
        url_imagen="https://cdn.ejemplo.com/a.jpg",
    )
    respuesta = await cliente.get(URL, headers={"X-API-Key": key})
    assert set(respuesta.json()) == {"datos"}
    noticia = respuesta.json()["datos"][0]
    assert set(noticia) == {
        "id",
        "titulo",
        "contenido",
        "url_imagen",
        "fecha_publicacion",
        "fecha_actualizacion",
    }
    assert noticia["titulo"] == "Con contenido"
    assert noticia["contenido"] == "<p>Hola</p>"
    assert noticia["url_imagen"] == "https://cdn.ejemplo.com/a.jpg"
    assert datetime.fromisoformat(noticia["fecha_publicacion"]).tzinfo is not None


async def test_contenido_e_imagen_nulos(cliente: httpx.AsyncClient, datos: Datos) -> None:
    _, key = await datos.api_key()
    await datos.noticia("Sin cuerpo", contenido=None, url_imagen=None)
    noticia = (await cliente.get(URL, headers={"X-API-Key": key})).json()["datos"][0]
    assert noticia["contenido"] is None
    assert noticia["url_imagen"] is None
