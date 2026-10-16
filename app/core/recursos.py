"""Recursos compartidos por la aplicación (engine, sesiones, Redis) y sus dependencias."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.redis_client import RedisSeguro


@dataclass(frozen=True)
class Recursos:
    settings: Settings
    engine: AsyncEngine
    sesiones: async_sessionmaker[AsyncSession]
    redis: RedisSeguro


def obtener_recursos(request: Request) -> Recursos:
    recursos = request.app.state.recursos
    if not isinstance(recursos, Recursos):
        raise RuntimeError("La aplicación no inicializó sus recursos (lifespan).")
    return recursos


async def obtener_sesion(request: Request) -> AsyncIterator[AsyncSession]:
    """Sesión por solicitud. No toma una conexión del pool hasta la primera consulta."""
    async with obtener_recursos(request).sesiones() as sesion:
        yield sesion


RecursosApp = Annotated[Recursos, Depends(obtener_recursos)]
Sesion = Annotated[AsyncSession, Depends(obtener_sesion)]
