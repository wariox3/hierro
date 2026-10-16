import httpx

from app.core.config import Settings
from app.main import create_app
from tests.conftest import CrearCliente


async def test_health_no_depende_de_la_base_ni_de_redis() -> None:
    # Sin lifespan: no existen engine ni cliente Redis.
    settings = Settings(_env_file=None, database_url="postgresql+asyncpg://u:p@localhost:1/x")
    app = create_app(settings)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as cliente:
        respuesta = await cliente.get("/health")
    assert respuesta.status_code == 200
    assert respuesta.json() == {"estado": "ok"}
    assert respuesta.headers["cache-control"] == "no-store"


async def test_ready_con_dependencias_disponibles(cliente: httpx.AsyncClient) -> None:
    respuesta = await cliente.get("/ready")
    assert respuesta.status_code == 200
    assert respuesta.json() == {
        "estado": "ok",
        "componentes": {"postgresql": "ok", "redis": "ok"},
    }


async def test_ready_falla_si_redis_no_responde(crear_cliente: CrearCliente) -> None:
    async with crear_cliente(redis_url="redis://localhost:1/0") as cliente:
        respuesta = await cliente.get("/ready")
    assert respuesta.status_code == 503
    assert respuesta.json()["componentes"] == {"postgresql": "ok", "redis": "error"}


async def test_ready_falla_si_postgresql_no_responde(crear_cliente: CrearCliente) -> None:
    async with crear_cliente(database_url="postgresql+asyncpg://u:p@localhost:1/x") as cliente:
        respuesta = await cliente.get("/ready")
    assert respuesta.status_code == 503
    assert respuesta.json()["componentes"] == {"postgresql": "error", "redis": "ok"}
