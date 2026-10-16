"""Consultas de lectura. Aquí vive la regla de visibilidad de las noticias."""

from datetime import datetime
from typing import Any

from sqlalchemy import ColumnElement, Row, Select, false, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Noticia as NoticiaModelo
from app.schemas import Noticia
from app.utilidades.paginacion import Paginacion, aplicar_pagina
from app.utilidades.sanitizacion import sanitizar_html


def condiciones_visibilidad() -> list[ColumnElement[bool]]:
    """Una noticia es visible solo si se cumple todo lo siguiente (igual para todas las keys)."""
    return [
        # `= false` (no `IS FALSE`) para que el planner use el índice parcial.
        NoticiaModelo.estado_inactivo == false(),
        NoticiaModelo.fecha_publicacion <= func.now(),
    ]


def _consulta_base() -> Select[*tuple[Any, ...]]:
    return select(
        NoticiaModelo.id,
        NoticiaModelo.titulo,
        NoticiaModelo.contenido,
        NoticiaModelo.url_imagen,
        NoticiaModelo.fecha_publicacion,
        NoticiaModelo.fecha_actualizacion,
    ).where(*condiciones_visibilidad())


def _a_esquema(fila: Row[Any]) -> Noticia:
    contenido = fila.contenido
    return Noticia(
        id=fila.id,
        titulo=fila.titulo,
        contenido=sanitizar_html(contenido) if isinstance(contenido, str) else None,
        url_imagen=fila.url_imagen,
        fecha_publicacion=fila.fecha_publicacion,
        fecha_actualizacion=fila.fecha_actualizacion,
    )


async def listar_noticias(
    sesion: AsyncSession,
    *,
    paginacion: Paginacion,
    actualizadas_desde: datetime | None = None,
) -> list[Noticia]:
    """Página ordenada por fecha de publicación descendente (desempate por id).

    Devuelve hasta `limite + 1` filas: la extra indica que hay otra página.
    """
    consulta = _consulta_base()
    if actualizadas_desde is not None:
        # También entran las programadas que se hicieron visibles después de esa fecha,
        # aunque su fila no se haya modificado.
        consulta = consulta.where(
            or_(
                NoticiaModelo.fecha_actualizacion >= actualizadas_desde,
                NoticiaModelo.fecha_publicacion >= actualizadas_desde,
            )
        )
    consulta = aplicar_pagina(
        consulta,
        fecha=NoticiaModelo.fecha_publicacion,
        id_=NoticiaModelo.id,
        paginacion=paginacion,
    )
    filas = await sesion.execute(consulta)
    return [_a_esquema(fila) for fila in filas]


async def obtener_noticia(sesion: AsyncSession, *, noticia_id: int) -> Noticia | None:
    consulta = _consulta_base().where(NoticiaModelo.id == noticia_id)
    fila = (await sesion.execute(consulta)).one_or_none()
    return _a_esquema(fila) if fila is not None else None
