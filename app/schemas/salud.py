"""Respuesta de /health."""

from typing import Literal

from pydantic import BaseModel


class EstadoSalud(BaseModel):
    estado: Literal["ok"]
