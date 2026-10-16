"""Errores de la API con un formato JSON uniforme."""

from collections.abc import Mapping

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging_config import request_id_actual
from app.schemas import DetalleError, ErrorCampo, ErrorRespuesta

_ERRORES_HTTP: dict[int, tuple[str, str]] = {
    400: ("solicitud_invalida", "Solicitud inválida."),
    401: ("no_autorizado", "No autorizado."),
    403: ("prohibido", "Acceso prohibido."),
    404: ("no_encontrado", "Recurso no encontrado."),
    405: ("metodo_no_permitido", "Método no permitido."),
    429: ("limite_excedido", "Demasiadas solicitudes."),
}

RESPUESTAS_ERROR_AUTH: dict[int | str, dict[str, object]] = {
    401: {"model": ErrorRespuesta, "description": "Falta la API key o no es válida."},
    403: {"model": ErrorRespuesta, "description": "La API key está inactiva."},
    429: {"model": ErrorRespuesta, "description": "Límite de solicitudes excedido."},
}


class ErrorAPI(Exception):
    """Error esperado que se convierte en una respuesta JSON con el formato estándar."""

    def __init__(
        self, estado: int, codigo: str, mensaje: str, headers: dict[str, str] | None = None
    ) -> None:
        super().__init__(mensaje)
        self.estado = estado
        self.codigo = codigo
        self.mensaje = mensaje
        self.headers = headers


def respuesta_error(
    estado: int,
    codigo: str,
    mensaje: str,
    *,
    headers: Mapping[str, str] | None = None,
    detalles: list[ErrorCampo] | None = None,
) -> JSONResponse:
    cuerpo = ErrorRespuesta(
        error=DetalleError(
            codigo=codigo, mensaje=mensaje, request_id=request_id_actual.get(), detalles=detalles
        )
    )
    return JSONResponse(
        cuerpo.model_dump(mode="json", exclude_none=True),
        status_code=estado,
        headers={"Cache-Control": "no-store", **(headers or {})},
    )


def registrar_manejadores(app: FastAPI) -> None:
    @app.exception_handler(ErrorAPI)
    async def _error_api(_: Request, exc: ErrorAPI) -> JSONResponse:
        return respuesta_error(exc.estado, exc.codigo, exc.mensaje, headers=exc.headers)

    @app.exception_handler(StarletteHTTPException)
    async def _error_http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        codigo, mensaje = _ERRORES_HTTP.get(exc.status_code, ("error_http", str(exc.detail)))
        return respuesta_error(exc.status_code, codigo, mensaje, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def _error_validacion(_: Request, exc: RequestValidationError) -> JSONResponse:
        detalles = [
            ErrorCampo(campo=".".join(str(parte) for parte in error["loc"]), mensaje=error["msg"])
            for error in exc.errors()
        ]
        return respuesta_error(
            422, "parametros_invalidos", "Parámetros inválidos.", detalles=detalles
        )
