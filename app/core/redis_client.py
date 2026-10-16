"""Cliente Redis tolerante a fallos.

Si Redis no está disponible, la API debe seguir funcionando contra PostgreSQL:
cada operación registra el error y devuelve un valor neutro en lugar de fallar.

El Redis administrado es compartido: todas las claves llevan el prefijo de
`REDIS_KEY_PREFIX` (p. ej. `hierro:produccion:`), que se agrega aquí y en ningún otro lado.
"""

import logging
import time

from redis.asyncio import Redis
from redis.exceptions import RedisError

logger = logging.getLogger("app.redis")

_ERRORES = (RedisError, OSError, TimeoutError)


class RedisSeguro:
    def __init__(self, cliente: Redis, prefijo: str, intervalo_log: float = 30.0) -> None:
        self._cliente = cliente
        self._prefijo = f"{prefijo}:"
        self._intervalo_log = intervalo_log
        self._ultimo_log = float("-inf")

    @classmethod
    def desde_url(cls, url: str, timeout: float, prefijo: str) -> "RedisSeguro":
        cliente = Redis.from_url(
            url,
            socket_timeout=timeout,
            socket_connect_timeout=timeout,
            health_check_interval=30,
        )
        return cls(cliente, prefijo)

    def _clave(self, clave: str) -> str:
        return self._prefijo + clave

    def _registrar_fallo(self, operacion: str, error: BaseException) -> None:
        # Con Redis caído cada solicitud fallaría: se limita la frecuencia del warning.
        ahora = time.monotonic()
        nivel = logging.DEBUG
        if ahora - self._ultimo_log >= self._intervalo_log:
            self._ultimo_log = ahora
            nivel = logging.WARNING
        logger.log(
            nivel, "redis_no_disponible", extra={"operacion": operacion, "error": repr(error)}
        )

    async def get(self, clave: str) -> bytes | None:
        try:
            valor = await self._cliente.get(self._clave(clave))
        except _ERRORES as error:
            self._registrar_fallo("get", error)
            return None
        return valor if isinstance(valor, bytes) else None

    async def set(self, clave: str, valor: bytes, ttl: int) -> None:
        try:
            await self._cliente.set(self._clave(clave), valor, ex=ttl)
        except _ERRORES as error:
            self._registrar_fallo("set", error)

    async def delete(self, *claves: str) -> None:
        try:
            await self._cliente.delete(*(self._clave(clave) for clave in claves))
        except _ERRORES as error:
            self._registrar_fallo("delete", error)

    async def incrementar(self, clave: str, ttl: int) -> int | None:
        """INCR con expiración fijada en el primer incremento. None si Redis falla."""
        try:
            async with self._cliente.pipeline(transaction=True) as pipe:
                pipe.incr(self._clave(clave))
                pipe.expire(self._clave(clave), ttl, nx=True)
                resultado = await pipe.execute()
        except _ERRORES as error:
            self._registrar_fallo("incrementar", error)
            return None
        return int(resultado[0])

    async def cerrar(self) -> None:
        await self._cliente.aclose()
