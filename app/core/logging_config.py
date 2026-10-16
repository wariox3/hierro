"""Logs estructurados en JSON hacia stdout (los recoge journald)."""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import TextIO

request_id_actual: ContextVar[str | None] = ContextVar("request_id_actual", default=None)

_ATRIBUTOS_ESTANDAR = frozenset(vars(logging.makeLogRecord({}))) | {
    "message",
    "asctime",
    "color_message",
    "taskName",
}


class FormateadorJSON(logging.Formatter):
    """Una línea JSON por registro, con el request ID y los campos de `extra`."""

    def format(self, record: logging.LogRecord) -> str:
        datos: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(
                timespec="milliseconds"
            ),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = request_id_actual.get()
        if request_id is not None:
            datos["request_id"] = request_id
        for clave, valor in vars(record).items():
            if clave not in _ATRIBUTOS_ESTANDAR and not clave.startswith("_"):
                datos[clave] = valor
        if record.exc_info:
            datos["exception"] = self.formatException(record.exc_info)
        return json.dumps(datos, ensure_ascii=False, default=str)


class _ManejadorServicio(logging.StreamHandler[TextIO]):
    """Marca el manejador propio para poder reemplazarlo sin tocar los ajenos."""


def configurar_logging(nivel: str) -> None:
    raiz = logging.getLogger()
    for manejador in [m for m in raiz.handlers if isinstance(m, _ManejadorServicio)]:
        raiz.removeHandler(manejador)
    nuevo = _ManejadorServicio(sys.stdout)
    nuevo.setFormatter(FormateadorJSON())
    raiz.addHandler(nuevo)
    raiz.setLevel(nivel)
    # Uvicorn trae sus propios manejadores de texto: se redirigen al JSON.
    for nombre in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        registro = logging.getLogger(nombre)
        registro.handlers.clear()
        registro.propagate = True
