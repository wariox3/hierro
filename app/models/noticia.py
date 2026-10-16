from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Identity,
    Index,
    Integer,
    String,
    Text,
    false,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Noticia(Base):
    __tablename__ = "noticia"
    __table_args__ = (
        CheckConstraint("length(btrim(titulo)) > 0", name="titulo_no_vacio"),
        CheckConstraint("url_imagen ~ '^https://[^[:space:]]+$'", name="url_imagen_https"),
        Index(
            "ix_noticia_publicacion_activa",
            text("fecha_publicacion DESC"),
            text("id DESC"),
            postgresql_where=text("estado_inactivo = false"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(always=True), primary_key=True)
    titulo: Mapped[str] = mapped_column(String(200))
    contenido: Mapped[str | None] = mapped_column(Text)
    url_imagen: Mapped[str | None] = mapped_column(String(500))
    fecha_publicacion: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    estado_inactivo: Mapped[bool] = mapped_column(server_default=false())
    fecha_creacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # La actualiza el trigger tg_noticia_fecha_actualizacion en cada UPDATE.
    fecha_actualizacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
