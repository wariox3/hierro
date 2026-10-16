"""Respuestas de noticias."""

from datetime import datetime

from pydantic import BaseModel, Field


class Noticia(BaseModel):
    id: int
    titulo: str
    contenido: str | None = Field(description="Cuerpo de la noticia en HTML sanitizado.")
    url_imagen: str | None = Field(examples=["https://cdn.ejemplo.com/imagen.jpg"])
    fecha_publicacion: datetime
    fecha_actualizacion: datetime


class ListaNoticias(BaseModel):
    """Listado sin paginación: no lleva `siguiente_cursor`."""

    datos: list[Noticia]
