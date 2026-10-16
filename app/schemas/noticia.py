"""Respuestas de noticias."""

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.paginacion import Pagina


class Noticia(BaseModel):
    id: int
    titulo: str
    contenido: str | None = Field(description="Cuerpo de la noticia en HTML sanitizado.")
    url_imagen: str | None = Field(examples=["https://cdn.ejemplo.com/imagen.jpg"])
    fecha_publicacion: datetime
    fecha_actualizacion: datetime


class ListaNoticias(Pagina[Noticia]):
    pass
