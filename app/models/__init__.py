"""Modelos ORM, uno por archivo. El esquema real lo crean las migraciones de Alembic.

Todo modelo nuevo debe importarse aquí: así queda registrado en `Base.metadata`
(lo usan Alembic y las claves foráneas declaradas por nombre de tabla) y se puede
importar como `from app.models import Modelo`.
"""

from app.core.db import Base
from app.models.api_key import ApiKey
from app.models.noticia import Noticia

__all__ = [
    "ApiKey",
    "Base",
    "Noticia",
]
