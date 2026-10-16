"""Endpoints de salud del servicio."""

import asyncio
import logging

from fastapi import APIRouter, Response
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.recursos import RecursosApp
from app.schemas import EstadoPreparacion, EstadoSalud

logger = logging.getLogger("app.salud")

router = APIRouter(tags=["salud"])

_SIN_CACHE = {"Cache-Control": "no-store"}


@router.get("/health", summary="Liveness: el proceso responde (sin dependencias).")
async def health(response: Response) -> EstadoSalud:
    response.headers.update(_SIN_CACHE)
    return EstadoSalud(estado="ok")
