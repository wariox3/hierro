"""Endpoints de salud del servicio."""

from fastapi import APIRouter, Response

from app.schemas import EstadoSalud

router = APIRouter(tags=["salud"])

_SIN_CACHE = {"Cache-Control": "no-store"}


@router.get("/health", summary="Liveness: el proceso responde (sin dependencias).")
async def health(response: Response) -> EstadoSalud:
    response.headers.update(_SIN_CACHE)
    return EstadoSalud(estado="ok")
