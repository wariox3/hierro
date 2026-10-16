"""El esquema creado por `alembic upgrade head`: índices, restricciones y trigger."""

import subprocess
import sys
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings
from tests.conftest import RAIZ, Datos

_ANTIGUA = datetime(2020, 1, 1, tzinfo=UTC)


async def _fechas(db: AsyncEngine, noticia_id: int) -> tuple[datetime, datetime]:
    async with db.connect() as conexion:
        fila = (
            await conexion.execute(
                text("SELECT fecha_creacion, fecha_actualizacion FROM noticia WHERE id = :id"),
                {"id": noticia_id},
            )
        ).one()
    return fila[0], fila[1]


async def test_trigger_actualiza_fecha_actualizacion(datos: Datos, db: AsyncEngine) -> None:
    noticia = await datos.noticia(fecha_actualizacion=_ANTIGUA)
    creacion, actualizacion = await _fechas(db, noticia.id)
    assert actualizacion == _ANTIGUA

    await datos.ejecutar(
        "UPDATE noticia SET titulo = 'Editada' WHERE id = :id",
        id=noticia.id,
    )
    creacion_despues, actualizacion_despues = await _fechas(db, noticia.id)
    assert actualizacion_despues > _ANTIGUA
    assert abs((datetime.now(UTC) - actualizacion_despues).total_seconds()) < 60
    assert creacion_despues == creacion


async def test_trigger_ignora_valor_explicito_en_update(datos: Datos, db: AsyncEngine) -> None:
    noticia = await datos.noticia()
    await datos.ejecutar(
        "UPDATE noticia SET fecha_actualizacion = '2000-01-01' WHERE id = :id",
        id=noticia.id,
    )
    _, actualizacion = await _fechas(db, noticia.id)
    assert actualizacion > _ANTIGUA


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO noticia (titulo, fecha_publicacion) VALUES ('   ', now())",
        "INSERT INTO noticia (titulo, fecha_publicacion, url_imagen) "
        "VALUES ('T', now(), 'http://inseguro.com/a.jpg')",
    ],
)
async def test_restricciones_check(datos: Datos, sql: str) -> None:
    with pytest.raises(IntegrityError):
        await datos.ejecutar(sql)


async def test_indices_esperados(db: AsyncEngine) -> None:
    async with db.connect() as conexion:
        filas = await conexion.execute(
            text("SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = 'public'")
        )
        indices: dict[str, str] = {str(fila[0]): str(fila[1]) for fila in filas}
    assert "WHERE (estado_inactivo = false)" in indices["ix_noticia_publicacion_activa"]
    assert "fecha_publicacion DESC, id DESC" in (indices["ix_noticia_publicacion_activa"])
    assert "ix_noticia_fecha_actualizacion" in indices


def test_modelos_coinciden_con_migraciones(settings: Settings) -> None:
    resultado = subprocess.run(
        [sys.executable, "-m", "alembic", "check"],
        cwd=RAIZ,
        env={
            "PATH": "",
            "DATABASE_URL": settings.database_url,
            "DATABASE_SSL": "disable",
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
