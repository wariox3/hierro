"""Esquemas Pydantic de las respuestas de la API, agrupados por dominio.

Se reexportan aquí para poder importarlos como `from app.schemas import Esquema`.
"""

from app.schemas.errores import DetalleError, ErrorCampo, ErrorRespuesta
from app.schemas.noticia import ListaNoticias, Noticia
from app.schemas.paginacion import Pagina
from app.schemas.salud import EstadoSalud

__all__ = [
    "DetalleError",
    "ErrorCampo",
    "ErrorRespuesta",
    "EstadoSalud",
    "ListaNoticias",
    "Noticia",
    "Pagina",
]
