"""Respuestas de /health y /ready."""

from typing import Literal

from pydantic import BaseModel, Field


class EstadoSalud(BaseModel):
    estado: Literal["ok"]


class EstadoPreparacion(BaseModel):
    estado: Literal["ok", "no_disponible"]
    componentes: dict[str, Literal["ok", "error"]] = Field(
        examples=[{"postgresql": "ok", "redis": "ok"}]
    )
