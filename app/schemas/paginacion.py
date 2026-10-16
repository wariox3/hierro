"""Envoltorio común de las respuestas paginadas."""

from pydantic import BaseModel, Field


class Pagina[T](BaseModel):
    datos: list[T]
    siguiente_cursor: str | None = Field(
        description="Cursor opaco para pedir la página siguiente; null si no hay más."
    )
