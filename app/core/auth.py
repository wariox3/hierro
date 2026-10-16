"""Autenticación por API key (header `X-API-Key`) y rate limiting por key."""

import time
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request, Security
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api_keys import hash_api_key
from app.core.errors import ErrorAPI
from app.core.recursos import RecursosApp, Sesion
from app.models import ApiKey

esquema_api_key = APIKeyHeader(
    name="X-API-Key", auto_error=False, description="API key del cliente."
)

_LARGO_MAXIMO_KEY = 256
# Las keys inexistentes también se cachean (menos tiempo) para no consultar la base
# con cada intento inválido.
_TTL_KEY_INEXISTENTE = 60
_WWW_AUTHENTICATE = {"WWW-Authenticate": "ApiKey"}


@dataclass(frozen=True)
class ApiKeyAutenticada:
    id: int
    nombre: str


class _EntradaCache(BaseModel):
    id: int | None = None  # None: la key no existe.
    nombre: str = ""
    activa: bool = False


def clave_cache_auth(hash_key: str) -> str:
    return f"news:v1:auth:{hash_key}"


def _leer_cache(valor: bytes | None) -> _EntradaCache | None:
    if valor is None:
        return None
    try:
        return _EntradaCache.model_validate_json(valor)
    except ValidationError:
        return None


async def _buscar_api_key(sesion: AsyncSession, hash_key: str) -> _EntradaCache:
    fila = (
        await sesion.execute(
            select(ApiKey.id, ApiKey.nombre, ApiKey.estado_inactivo).where(ApiKey.hash == hash_key)
        )
    ).one_or_none()
    if fila is None:
        return _EntradaCache()
    return _EntradaCache(id=fila[0], nombre=fila[1], activa=not fila[2])


def _key_invalida() -> ErrorAPI:
    return ErrorAPI(401, "api_key_invalida", "La API key no es válida.", _WWW_AUTHENTICATE)


async def autenticar(
    request: Request,
    recursos: RecursosApp,
    sesion: Sesion,
    api_key: Annotated[str | None, Security(esquema_api_key)],
) -> ApiKeyAutenticada:
    if not api_key:
        raise ErrorAPI(401, "api_key_requerida", "Falta el header X-API-Key.", _WWW_AUTHENTICATE)
    if len(api_key) > _LARGO_MAXIMO_KEY:
        raise _key_invalida()

    hash_key = hash_api_key(api_key)
    clave = clave_cache_auth(hash_key)
    entrada = _leer_cache(await recursos.redis.get(clave))
    if entrada is None:
        entrada = await _buscar_api_key(sesion, hash_key)
        ttl = recursos.settings.auth_cache_ttl
        if entrada.id is None:
            ttl = min(ttl, _TTL_KEY_INEXISTENTE)
        await recursos.redis.set(clave, entrada.model_dump_json().encode(), ttl)

    if entrada.id is None:
        raise _key_invalida()
    if not entrada.activa:
        raise ErrorAPI(403, "api_key_inactiva", "La API key está inactiva.")
    # Para el log de acceso.
    request.state.api_key_id = entrada.id
    return ApiKeyAutenticada(id=entrada.id, nombre=entrada.nombre)


async def limitar_tasa(
    recursos: RecursosApp,
    api_key: Annotated[ApiKeyAutenticada, Depends(autenticar)],
) -> ApiKeyAutenticada:
    """Ventana fija por API key. Si Redis falla, deja pasar (y queda en el log)."""
    limite = recursos.settings.rate_limit_requests
    ventana = recursos.settings.rate_limit_window
    ahora = int(time.time())
    cuenta = await recursos.redis.incrementar(
        f"news:v1:rl:{api_key.id}:{ahora // ventana}", ttl=ventana
    )
    if cuenta is not None and cuenta > limite:
        raise ErrorAPI(
            429,
            "limite_excedido",
            "Se excedió el límite de solicitudes; reintenta más tarde.",
            {"Retry-After": str(ventana - ahora % ventana), "X-RateLimit-Limit": str(limite)},
        )
    return api_key


ApiKeyActual = Annotated[ApiKeyAutenticada, Depends(limitar_tasa)]
