"""Alta, rotación y listado de API keys (lo usa scripts/crear_api_key.py)."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.api_keys import generar_api_key
from app.core.auth import clave_cache_auth
from app.core.redis_client import RedisSeguro
from app.models import ApiKey


class ErrorGestion(Exception):
    """Error esperado, con un mensaje para mostrar al operador."""


async def crear_api_key(
    sesiones: async_sessionmaker[AsyncSession], nombre: str
) -> tuple[ApiKey, str]:
    """Crea la API key y la devuelve en claro (no se guarda en ningún lado)."""
    nombre = nombre.strip()
    if not nombre:
        raise ErrorGestion("El nombre no puede estar vacío.")
    generada = generar_api_key()
    api_key = ApiKey(nombre=nombre, hash=generada.hash, prefijo=generada.prefijo)
    try:
        async with sesiones() as sesion, sesion.begin():
            sesion.add(api_key)
    except IntegrityError as error:
        raise ErrorGestion(f"Ya existe una API key llamada {nombre!r}.") from error
    return api_key, generada.key


async def rotar_api_key(
    sesiones: async_sessionmaker[AsyncSession], redis: RedisSeguro | None, nombre: str
) -> tuple[ApiKey, str]:
    """Reemplaza la key manteniendo el registro. La anterior deja de funcionar de inmediato."""
    generada = generar_api_key()
    async with sesiones() as sesion, sesion.begin():
        api_key = (
            await sesion.execute(select(ApiKey).where(ApiKey.nombre == nombre).with_for_update())
        ).scalar_one_or_none()
        if api_key is None:
            raise ErrorGestion(f"No existe una API key llamada {nombre!r}.")
        hash_anterior = api_key.hash
        api_key.hash = generada.hash
        api_key.prefijo = generada.prefijo
    # Sin esto la key anterior seguiría válida hasta que expire su entrada en la caché.
    if redis is not None:
        await redis.delete(clave_cache_auth(hash_anterior))
    return api_key, generada.key


async def listar_api_keys(sesiones: async_sessionmaker[AsyncSession]) -> list[ApiKey]:
    async with sesiones() as sesion:
        resultado = await sesion.execute(select(ApiKey).order_by(ApiKey.id))
        return list(resultado.scalars())
