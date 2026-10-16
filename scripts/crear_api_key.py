"""Gestiona las API keys de los clientes de la API.

Usa ADMIN_DATABASE_URL (rol propietario), o DATABASE_URL si no está definida.

    .venv/bin/python scripts/crear_api_key.py crear "web"
    .venv/bin/python scripts/crear_api_key.py rotar "web"
    .venv/bin/python scripts/crear_api_key.py listar

La API key se muestra UNA ÚNICA VEZ: en la base solo quedan su hash SHA-256 y su prefijo.
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import Settings
from app.core.db import crear_engine
from app.core.redis_client import RedisSeguro
from app.utilidades.gestion_api_keys import (
    ErrorGestion,
    crear_api_key,
    listar_api_keys,
    rotar_api_key,
)


def _mostrar_key(accion: str, nombre: str, id_: int, key: str) -> None:
    print(f"API key {accion}: {nombre} (id {id_})")
    print()
    print(f"  {key}")
    print()
    print("Guárdala ahora en un gestor de secretos: no se volverá a mostrar.")


async def _ejecutar(argumentos: argparse.Namespace) -> int:
    settings = Settings()
    engine = crear_engine(settings, settings.url_admin)
    sesiones = async_sessionmaker(engine, expire_on_commit=False)
    redis = RedisSeguro.desde_url(
        settings.redis_url, settings.redis_timeout, settings.redis_key_prefix
    )
    try:
        if argumentos.comando == "crear":
            api_key, key = await crear_api_key(sesiones, argumentos.nombre)
            _mostrar_key("creada", api_key.nombre, api_key.id, key)
        elif argumentos.comando == "rotar":
            api_key, key = await rotar_api_key(sesiones, redis, argumentos.nombre)
            _mostrar_key("rotada", api_key.nombre, api_key.id, key)
            print("La key anterior dejó de funcionar.")
        else:
            print(f"{'id':>4}  {'nombre':<30} {'prefijo':<14} {'estado':<9} creada")
            for api_key in await listar_api_keys(sesiones):
                estado = "inactiva" if api_key.estado_inactivo else "activa"
                print(
                    f"{api_key.id:>4}  {api_key.nombre:<30} "
                    f"{api_key.prefijo:<14} {estado:<9} {api_key.fecha_creacion:%Y-%m-%d}"
                )
    except ErrorGestion as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    finally:
        await redis.cerrar()
        await engine.dispose()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gestiona las API keys de los clientes.")
    comandos = parser.add_subparsers(dest="comando", required=True)
    comandos.add_parser("crear", help="Crea una API key nueva.").add_argument("nombre")
    comandos.add_parser("rotar", help="Genera una key nueva e invalida la anterior.").add_argument(
        "nombre"
    )
    comandos.add_parser("listar", help="Lista las API keys (sin mostrarlas).")
    return asyncio.run(_ejecutar(parser.parse_args(argv)))


if __name__ == "__main__":
    sys.exit(main())
