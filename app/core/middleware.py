"""Middleware ASGI: request ID, log de acceso y captura de errores no controlados."""

import logging
import re
import time
import uuid

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.errors import respuesta_error
from app.core.logging_config import request_id_actual

logger = logging.getLogger("app.acceso")

_REQUEST_ID_VALIDO = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


class MiddlewareSolicitud:
    """Asigna un request ID (propio o del header `X-Request-ID`) y lo devuelve en la respuesta."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        recibido = Headers(scope=scope).get("x-request-id")
        request_id = (
            recibido if recibido and _REQUEST_ID_VALIDO.match(recibido) else uuid.uuid4().hex
        )
        token = request_id_actual.set(request_id)
        inicio = time.perf_counter()
        estado = 500
        iniciada = False

        async def enviar(mensaje: Message) -> None:
            nonlocal estado, iniciada
            if mensaje["type"] == "http.response.start":
                iniciada = True
                estado = mensaje["status"]
                MutableHeaders(scope=mensaje).append("X-Request-ID", request_id)
            await send(mensaje)

        try:
            await self.app(scope, receive, enviar)
        except Exception:
            logger.exception("error_no_controlado")
            if iniciada:
                raise
            respuesta = respuesta_error(500, "error_interno", "Error interno del servidor.")
            await respuesta(scope, receive, enviar)
        finally:
            cliente = scope.get("client")
            logger.info(
                "solicitud",
                extra={
                    "metodo": scope["method"],
                    "ruta": scope["path"],
                    "estado": estado,
                    "duracion_ms": round((time.perf_counter() - inicio) * 1000, 2),
                    "cliente": cliente[0] if cliente else None,
                    "api_key_id": scope.get("state", {}).get("api_key_id"),
                },
            )
            request_id_actual.reset(token)
