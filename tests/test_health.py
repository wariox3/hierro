import httpx

from app.core.config import Settings
from app.main import create_app


async def test_health_no_depende_de_la_base_ni_de_redis() -> None:
    # Sin lifespan: no existen engine ni cliente Redis.
    settings = Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://u:p@localhost:1/x",
        redis_key_prefix="hierro:test",
    )
    app = create_app(settings)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as cliente:
        respuesta = await cliente.get("/health")
    assert respuesta.status_code == 200
    assert respuesta.json() == {"estado": "ok"}
    assert respuesta.headers["cache-control"] == "no-store"
