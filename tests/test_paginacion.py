"""Paginación por cursor común a los listados (`app/utilidades/paginacion.py`).

Ningún endpoint la usa hoy (`/noticias/v1/lista` es la excepción, sin paginación), así
que se prueba con una app mínima y con consultas directas a la base.
"""

import base64
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import false, select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.errors import ErrorAPI, registrar_manejadores
from app.models import Noticia as NoticiaModelo
from app.utilidades.paginacion import (
    Paginacion,
    ParametrosPaginacion,
    aplicar_pagina,
    codificar_cursor,
    cortar_pagina,
    decodificar_cursor,
)
from tests.conftest import Datos

AHORA = datetime.now(UTC)


# --- Cursor --------------------------------------------------------------------


def test_cursor_ida_y_vuelta() -> None:
    fecha = datetime(2026, 10, 16, 12, 30, tzinfo=UTC)
    cursor = codificar_cursor(fecha, 42)
    assert "=" not in cursor
    assert decodificar_cursor(cursor) == (fecha, 42)


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
def test_cursor_invalido(cursor: str) -> None:
    with pytest.raises(ErrorAPI) as error:
        decodificar_cursor(cursor)
    assert error.value.estado == 400
    assert error.value.codigo == "cursor_invalido"


# --- Parámetros (limit y cursor) -----------------------------------------------


@pytest.fixture
async def cliente_paginado() -> AsyncIterator[httpx.AsyncClient]:
    app = FastAPI()
    registrar_manejadores(app)

    @app.get("/items")
    async def items(paginacion: ParametrosPaginacion) -> dict[str, object]:
        return {"limite": paginacion.limite, "despues_de": paginacion.despues_de is not None}

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as cliente:
        yield cliente


async def test_limite_por_defecto_20(cliente_paginado: httpx.AsyncClient) -> None:
    respuesta = await cliente_paginado.get("/items")
    assert respuesta.json() == {"limite": 20, "despues_de": False}


async def test_cursor_valido_se_decodifica(cliente_paginado: httpx.AsyncClient) -> None:
    cursor = codificar_cursor(AHORA, 1)
    respuesta = await cliente_paginado.get("/items", params={"limit": 50, "cursor": cursor})
    assert respuesta.json() == {"limite": 50, "despues_de": True}


@pytest.mark.parametrize("limite", [0, 51, -1])
async def test_limite_fuera_de_rango_422(cliente_paginado: httpx.AsyncClient, limite: int) -> None:
    respuesta = await cliente_paginado.get("/items", params={"limit": limite})
    assert respuesta.status_code == 422
    assert respuesta.json()["error"]["codigo"] == "parametros_invalidos"


async def test_cursor_invalido_400(cliente_paginado: httpx.AsyncClient) -> None:
    respuesta = await cliente_paginado.get("/items", params={"cursor": "no-es-base64!!"})
    assert respuesta.status_code == 400
    assert respuesta.json()["error"]["codigo"] == "cursor_invalido"


# --- Consulta paginada ---------------------------------------------------------


async def _pagina(db: AsyncEngine, limite: int, cursor: str | None) -> tuple[list[int], str | None]:
    paginacion = Paginacion(
        limite=limite,
        cursor=cursor,
        despues_de=decodificar_cursor(cursor) if cursor else None,
    )
    consulta = aplicar_pagina(
        select(NoticiaModelo.id, NoticiaModelo.fecha_publicacion).where(
            NoticiaModelo.estado_inactivo == false()
        ),
        fecha=NoticiaModelo.fecha_publicacion,
        id_=NoticiaModelo.id,
        paginacion=paginacion,
    )
    async with db.connect() as conexion:
        filas = list(await conexion.execute(consulta))
    pagina, siguiente = cortar_pagina(filas, paginacion, lambda f: (f.fecha_publicacion, f.id))
    return [fila.id for fila in pagina], siguiente


async def test_recorre_todas_las_paginas_sin_duplicados(datos: Datos, db: AsyncEngine) -> None:
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
        ids, cursor = await _pagina(db, 2, cursor)
        vistos += ids
        paginas += 1
        if cursor is None:
            break

    assert vistos == esperado
    assert paginas == 4


async def test_ultima_pagina_exacta_no_tiene_cursor(datos: Datos, db: AsyncEngine) -> None:
    for i in range(2):
        await datos.noticia(f"N{i}")
    ids, siguiente = await _pagina(db, 2, None)
    assert len(ids) == 2
    assert siguiente is None
