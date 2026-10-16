"""Endpoints de noticias (solo lectura)."""

from fastapi import APIRouter, Request, Response
from sqlalchemy import false, select

from app.core.auth import ApiKeyActual
from app.core.cache import (
    RESPUESTA_NO_MODIFICADO,
    clave_cache,
    cuerpo_cacheado,
    respuesta_con_etag,
)
from app.core.errors import RESPUESTAS_ERROR_AUTH
from app.core.recursos import RecursosApp, Sesion
from app.models import Noticia as NoticiaModelo
from app.schemas import ListaNoticias, Noticia
from app.utilidades.sanitizacion import sanitizar_html

router = APIRouter(prefix="/v1", tags=["noticias"], responses=RESPUESTAS_ERROR_AUTH)


@router.get(
    "/lista",
    summary="Las últimas 10 noticias activas.",
    description=(
        "Ordenadas por fecha de publicación descendente. Sin paginación ni filtros. "
        "Incluye el `contenido` HTML sanitizado de cada noticia."
    ),
    response_model=ListaNoticias,
    responses=RESPUESTA_NO_MODIFICADO,
)
async def lista(
    request: Request,
    _: ApiKeyActual,
    recursos: RecursosApp,
    sesion: Sesion,
) -> Response:
    async def calcular() -> bytes:
        consulta = (
            select(
                NoticiaModelo.id,
                NoticiaModelo.titulo,
                NoticiaModelo.contenido,
                NoticiaModelo.url_imagen,
                NoticiaModelo.fecha_publicacion,
                NoticiaModelo.fecha_actualizacion,
            )
            # `= false` (no `IS FALSE`) para que el planner use el índice parcial.
            .where(NoticiaModelo.estado_inactivo == false())
            .order_by(NoticiaModelo.fecha_publicacion.desc(), NoticiaModelo.id.desc())
            .limit(10)
        )
        noticias = [
            Noticia(
                id=fila.id,
                titulo=fila.titulo,
                contenido=sanitizar_html(fila.contenido) if fila.contenido is not None else None,
                url_imagen=fila.url_imagen,
                fecha_publicacion=fila.fecha_publicacion,
                fecha_actualizacion=fila.fecha_actualizacion,
            )
            for fila in await sesion.execute(consulta)
        ]
        return ListaNoticias(datos=noticias).model_dump_json().encode()

    clave = clave_cache("noticias", {})
    cuerpo = await cuerpo_cacheado(recursos.redis, clave, recursos.settings.cache_ttl, calcular)
    return respuesta_con_etag(request, cuerpo, recursos.settings.http_cache_max_age)
