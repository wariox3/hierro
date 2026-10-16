"""Caché de respuestas en Redis y validación HTTP con ETag.

Los datos se cargan por SQL y la API no se entera: la caché expira por TTL.
"""

import hashlib
import json
from collections.abc import Awaitable, Callable, Mapping

from fastapi import Request, Response

from app.core.redis_client import RedisSeguro

RESPUESTA_NO_MODIFICADO: dict[int | str, dict[str, object]] = {
    304: {"description": "No modificado: el ETag de `If-None-Match` coincide."}
}


def clave_cache(recurso: str, parametros: Mapping[str, object]) -> str:
    """Clave con el recurso y un hash de los parámetros normalizados.

    No incluye la API key: todas las keys ven los mismos datos, así que comparten caché.
    """
    normalizados = json.dumps(parametros, sort_keys=True, default=str, separators=(",", ":"))
    huella = hashlib.sha256(normalizados.encode()).hexdigest()[:32]
    return f"v1:{recurso}:{huella}"


async def cuerpo_cacheado(
    redis: RedisSeguro, clave: str, ttl: int, calcular: Callable[[], Awaitable[bytes]]
) -> bytes:
    cuerpo = await redis.get(clave)
    if cuerpo is None:
        cuerpo = await calcular()
        await redis.set(clave, cuerpo, ttl)
    return cuerpo


def calcular_etag(cuerpo: bytes) -> str:
    return f'"{hashlib.sha256(cuerpo).hexdigest()[:32]}"'


def etag_coincide(if_none_match: str | None, etag: str) -> bool:
    """Comparación débil (RFC 9110): Nginx convierte el ETag en `W/"..."` al comprimir."""
    if not if_none_match:
        return False
    if if_none_match.strip() == "*":
        return True
    candidatos = (parte.strip().removeprefix("W/") for parte in if_none_match.split(","))
    return etag.removeprefix("W/") in candidatos


def respuesta_con_etag(request: Request, cuerpo: bytes, max_age: int) -> Response:
    etag = calcular_etag(cuerpo)
    headers = {
        "ETag": etag,
        "Cache-Control": f"private, max-age={max_age}",
        "Vary": "X-API-Key",
    }
    if etag_coincide(request.headers.get("if-none-match"), etag):
        return Response(status_code=304, headers=headers)
    return Response(cuerpo, media_type="application/json", headers=headers)
