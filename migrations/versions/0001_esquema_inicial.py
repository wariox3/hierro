"""Esquema inicial: API keys, noticias, índices y trigger.

Revision ID: 0001
Revises:
Create Date: 2026-10-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_AHORA = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "api_key",
        sa.Column("id", sa.Integer(), sa.Identity(always=True), nullable=False),
        sa.Column("nombre", sa.String(100), nullable=False),
        sa.Column("hash", sa.String(64), nullable=False),
        sa.Column("prefijo", sa.String(16), nullable=False),
        sa.Column("estado_inactivo", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column(
            "fecha_creacion", sa.DateTime(timezone=True), server_default=_AHORA, nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("nombre"),
        sa.UniqueConstraint("hash"),
        sa.CheckConstraint("hash ~ '^[0-9a-f]{64}$'", name="hash_formato"),
    )

    op.create_table(
        "noticia",
        sa.Column("id", sa.Integer(), sa.Identity(always=True), nullable=False),
        sa.Column("titulo", sa.String(200), nullable=False),
        sa.Column("contenido", sa.Text(), nullable=True),
        sa.Column("url_imagen", sa.String(500), nullable=True),
        sa.Column("fecha_publicacion", sa.DateTime(timezone=True), nullable=False),
        sa.Column("estado_inactivo", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column(
            "fecha_creacion", sa.DateTime(timezone=True), server_default=_AHORA, nullable=False
        ),
        sa.Column(
            "fecha_actualizacion",
            sa.DateTime(timezone=True),
            server_default=_AHORA,
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("length(btrim(titulo)) > 0", name="titulo_no_vacio"),
        sa.CheckConstraint("url_imagen ~ '^https://[^[:space:]]+$'", name="url_imagen_https"),
    )
    op.create_index("ix_noticia_fecha_actualizacion", "noticia", ["fecha_actualizacion"])
    op.create_index(
        "ix_noticia_publicacion_activa",
        "noticia",
        [sa.text("fecha_publicacion DESC"), sa.text("id DESC")],
        postgresql_where=sa.text("estado_inactivo = false"),
    )

    # PostgreSQL no tiene ON UPDATE: la fecha de actualización la mantiene un trigger.
    op.execute(
        """
        CREATE FUNCTION fn_actualizar_fecha_actualizacion() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            NEW.fecha_actualizacion := now();
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER tg_noticia_fecha_actualizacion
        BEFORE UPDATE ON noticia
        FOR EACH ROW EXECUTE FUNCTION fn_actualizar_fecha_actualizacion()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS tg_noticia_fecha_actualizacion ON noticia")
    op.execute("DROP FUNCTION IF EXISTS fn_actualizar_fecha_actualizacion()")
    op.drop_table("noticia")
    op.drop_table("api_key")
