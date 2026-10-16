"""Endpoints de noticias (solo lectura)."""

from datetime import UTC
from typing import Annotated

from fastapi import APIRouter, Path, Query, Request, Response
from pydantic import AwareDatetime

from app import repositorio
from app.core.auth import ApiKeyActual
from app.core.cache import (
    RESPUESTA_NO_MODIFICADO,
    clave_cache,
    cuerpo_cacheado,
    respuesta_con_etag,
)
from app.core.errors import RESPUESTAS_ERROR_AUTH, ErrorAPI
from app.core.recursos import RecursosApp, Sesion
from app.schemas import ErrorRespuesta, ListaNoticias, Noticia
from app.utilidades.paginacion import (
    RESPUESTA_CURSOR_INVALIDO,
    ParametrosPaginacion,
    cortar_pagina,
)

router = APIRouter(prefix="/v1", tags=["noticias"], responses=RESPUESTAS_ERROR_AUTH)

_ID_MAXIMO = 2_147_483_647

_PARAMETROS_INVALIDOS: dict[int | str, dict[str, object]] = {
    422: {"model": ErrorRespuesta, "description": "Parámetros inválidos."}
}


@router.get(
    "/noticias",
    summary="Listado de noticias visibles para la aplicación.",
    description=(
        "Ordenado por fecha de publicación descendente. Paginación por cursor: "
        "envía `siguiente_cursor` en `cursor` para pedir la página siguiente. "
        "Incluye el `contenido` HTML sanitizado de cada noticia."
    ),
    response_model=ListaNoticias,
    responses={
        **RESPUESTA_NO_MODIFICADO,
        **RESPUESTA_CURSOR_INVALIDO,
        **_PARAMETROS_INVALIDOS,
    },
)
async def listar_noticias(
    request: Request,
    _: ApiKeyActual,
    recursos: RecursosApp,
    sesion: Sesion,
    paginacion: ParametrosPaginacion,
    updated_since: Annotated[
        AwareDatetime | None,
        Query(
            description=(
                "Fecha ISO 8601 con zona horaria. Devuelve las noticias creadas, "
                "modificadas o publicadas desde esa fecha."
            ),
            examples=["2026-10-01T00:00:00Z"],
        ),
    ] = None,
) -> Response:
    desde = updated_since.astimezone(UTC) if updated_since else None
    parametros = {
        **paginacion.parametros_cache(),
        "updated_since": desde.isoformat() if desde else None,
    }

    async def calcular() -> bytes:
        filas = await repositorio.listar_noticias(
            sesion, paginacion=paginacion, actualizadas_desde=desde
        )
        noticias, siguiente = cortar_pagina(
            filas, paginacion, lambda n: (n.fecha_publicacion, n.id)
        )
        return ListaNoticias(datos=noticias, siguiente_cursor=siguiente).model_dump_json().encode()

    clave = clave_cache("noticias", parametros)
    cuerpo = await cuerpo_cacheado(recursos.redis, clave, recursos.settings.cache_ttl, calcular)
    return respuesta_con_etag(request, cuerpo, recursos.settings.http_cache_max_age)


@router.get(
    "/noticias/{noticia_id}",
    summary="Una noticia, con su contenido HTML sanitizado.",
    response_model=Noticia,
    responses={
        **RESPUESTA_NO_MODIFICADO,
        404: {
            "model": ErrorRespuesta,
            "description": "La noticia no existe o no es visible para la aplicación.",
        },
        **_PARAMETROS_INVALIDOS,
    },
)
async def obtener_noticia(
    request: Request,
    _: ApiKeyActual,
    recursos: RecursosApp,
    sesion: Sesion,
    noticia_id: Annotated[int, Path(ge=1, le=_ID_MAXIMO)],
) -> Response:
    async def calcular() -> bytes:
        noticia = await repositorio.obtener_noticia(sesion, noticia_id=noticia_id)
        if noticia is None:
            # Mismo 404 si no existe o si no es visible: no se revela cuál de los dos.
            raise ErrorAPI(404, "noticia_no_encontrada", "La noticia no existe.")
        return noticia.model_dump_json().encode()

    clave = clave_cache("noticia", {"id": noticia_id})
    cuerpo = await cuerpo_cacheado(recursos.redis, clave, recursos.settings.cache_ttl, calcular)
    return respuesta_con_etag(request, cuerpo, recursos.settings.http_cache_max_age)
