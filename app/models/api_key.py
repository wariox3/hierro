from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Identity, Integer, String, false, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ApiKey(Base):
    """API key de un cliente de la API. De la key solo se guardan su SHA-256 y su prefijo."""

    __tablename__ = "api_key"
    __table_args__ = (CheckConstraint("hash ~ '^[0-9a-f]{64}$'", name="hash_formato"),)

    id: Mapped[int] = mapped_column(Integer, Identity(always=True), primary_key=True)
    nombre: Mapped[str] = mapped_column(String(100), unique=True)
    hash: Mapped[str] = mapped_column(String(64), unique=True)
    prefijo: Mapped[str] = mapped_column(String(16))
    estado_inactivo: Mapped[bool] = mapped_column(server_default=false())
    fecha_creacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
