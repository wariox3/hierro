"""Construcción de la aplicación FastAPI.

Uvicorn la arranca con `app.main:create_app --factory`.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import async_sessionmaker

from app import __version__
from app.core.config import Settings, get_settings
from app.core.db import crear_engine
from app.core.errors import registrar_manejadores
from app.core.logging_config import configurar_logging
from app.core.middleware import MiddlewareSolicitud
from app.core.recursos import Recursos
from app.core.redis_client import RedisSeguro
from app.routers import health, noticias


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configurar_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = crear_engine(settings)
        redis = RedisSeguro.desde_url(settings.redis_url, settings.redis_timeout)
        app.state.recursos = Recursos(
            settings=settings,
            engine=engine,
            sesiones=async_sessionmaker(engine, expire_on_commit=False),
            redis=redis,
        )
        try:
            yield
        finally:
            await redis.cerrar()
            await engine.dispose()

    app = FastAPI(
        title="News Service",
        description="API REST de solo lectura que provee noticias a las aplicaciones cliente.",
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
    )
    registrar_manejadores(app)

    # CORS cerrado por defecto: solo se activa si hay orígenes configurados.
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_methods=["GET"],
            allow_headers=["X-API-Key", "X-Request-ID", "If-None-Match"],
            expose_headers=["ETag", "X-Request-ID", "Retry-After"],
            max_age=600,
        )
    # Se agrega al final para que sea el más externo.
    app.add_middleware(MiddlewareSolicitud)

    app.include_router(health.router)
    app.include_router(noticias.router)
    return app
