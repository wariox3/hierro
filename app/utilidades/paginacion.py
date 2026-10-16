"""Paginación por cursor, común a todos los listados de la API.

Todo listado se ordena por `(fecha, id)` descendente y se pagina por keyset:
  - la ruta recibe `limit` y `cursor` con la dependencia `ParametrosPaginacion`;
  - el repositorio filtra y ordena con `aplicar_pagina` (pide `limite + 1` filas);
  - la ruta corta el resultado con `cortar_pagina` y responde un `Pagina[T]`.

El cursor es opaco: base64url de `{"f": fecha, "i": id}` de la última fila de la página.
"""

import base64
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Any

from fastapi import Depends, Query
from sqlalchemy import DateTime, Integer, Select, literal, tuple_
from sqlalchemy.orm import InstrumentedAttribute

from app.core.errors import ErrorAPI
from app.schemas import ErrorRespuesta

LIMITE_POR_DEFECTO = 20
LIMITE_MAXIMO = 50

Posicion = tuple[datetime, int]


def codificar_cursor(fecha: datetime, fila_id: int) -> str:
    datos = json.dumps({"f": fecha.isoformat(), "i": fila_id}, separators=(",", ":"))
    return base64.urlsafe_b64encode(datos.encode()).decode().rstrip("=")


def _cursor_invalido() -> ErrorAPI:
    return ErrorAPI(400, "cursor_invalido", "El cursor de paginación no es válido.")


def decodificar_cursor(cursor: str) -> Posicion:
    try:
        crudo = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        datos = json.loads(crudo)
        fecha = datetime.fromisoformat(datos["f"])
        fila_id = datos["i"]
    except (ValueError, KeyError, TypeError) as error:
        raise _cursor_invalido() from error
    if fecha.tzinfo is None or type(fila_id) is not int:
        raise _cursor_invalido()
    return fecha, fila_id


@dataclass(frozen=True)
class Paginacion:
    limite: int
    cursor: str | None
    despues_de: Posicion | None

    def parametros_cache(self) -> dict[str, object]:
        return {"limit": self.limite, "cursor": self.cursor}


def obtener_paginacion(
    limit: Annotated[
        int,
        Query(ge=1, le=LIMITE_MAXIMO, description=f"Tamaño de página (máximo {LIMITE_MAXIMO})."),
    ] = LIMITE_POR_DEFECTO,
    cursor: Annotated[
        str | None,
        Query(max_length=200, description="`siguiente_cursor` de la página anterior."),
    ] = None,
) -> Paginacion:
    return Paginacion(
        limite=limit,
        cursor=cursor,
        despues_de=decodificar_cursor(cursor) if cursor else None,
    )


ParametrosPaginacion = Annotated[Paginacion, Depends(obtener_paginacion)]

RESPUESTA_CURSOR_INVALIDO: dict[int | str, dict[str, object]] = {
    400: {"model": ErrorRespuesta, "description": "Cursor inválido."},
}


def aplicar_pagina(
    consulta: Select[Any],
    *,
    fecha: InstrumentedAttribute[datetime],
    id_: InstrumentedAttribute[int],
    paginacion: Paginacion,
) -> Select[Any]:
    """Ordena por `(fecha, id)` descendente, salta hasta el cursor y pide `limite + 1` filas."""
    if paginacion.despues_de is not None:
        fecha_cursor, id_cursor = paginacion.despues_de
        consulta = consulta.where(
            tuple_(fecha, id_)
            < tuple_(
                literal(fecha_cursor, DateTime(timezone=True)),
                literal(id_cursor, Integer),
            )
        )
    return consulta.order_by(fecha.desc(), id_.desc()).limit(paginacion.limite + 1)


def cortar_pagina[T](
    filas: Sequence[T], paginacion: Paginacion, posicion: Callable[[T], Posicion]
) -> tuple[list[T], str | None]:
    """Recorta la fila extra y, si la había, devuelve el cursor de la página siguiente."""
    if len(filas) <= paginacion.limite:
        return list(filas), None
    pagina = list(filas[: paginacion.limite])
    return pagina, codificar_cursor(*posicion(pagina[-1]))
