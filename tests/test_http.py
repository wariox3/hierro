"""CORS, OpenAPI y logs JSON."""

import json
import logging

import httpx
import pytest

from app.core.logging_config import FormateadorJSON, request_id_actual
from tests.conftest import CrearCliente

_PREFLIGHT = {
    "Origin": "https://app.ejemplo.com",
    "Access-Control-Request-Method": "GET",
    "Access-Control-Request-Headers": "X-API-Key",
}


async def test_cors_cerrado_por_defecto(cliente: httpx.AsyncClient) -> None:
    respuesta = await cliente.options("/v1/noticias", headers=_PREFLIGHT)
    assert "access-control-allow-origin" not in respuesta.headers


async def test_cors_configurado(crear_cliente: CrearCliente) -> None:
    async with crear_cliente(cors_origins=["https://app.ejemplo.com"]) as cliente:
        permitido = await cliente.options("/v1/noticias", headers=_PREFLIGHT)
        otro = await cliente.options(
            "/v1/noticias", headers={**_PREFLIGHT, "Origin": "https://malo.com"}
        )
    assert permitido.status_code == 200
    assert permitido.headers["access-control-allow-origin"] == "https://app.ejemplo.com"
    assert "access-control-allow-origin" not in otro.headers


async def test_openapi_documenta_esquemas_y_seguridad(cliente: httpx.AsyncClient) -> None:
    esquema = (await cliente.get("/openapi.json")).json()
    assert set(esquema["paths"]) == {
        "/health",
        "/ready",
        "/v1/noticias",
        "/v1/noticias/{noticia_id}",
    }
    # Solo lectura: ningún endpoint de escritura.
    assert all(set(metodos) == {"get"} for metodos in esquema["paths"].values())
    assert esquema["components"]["securitySchemes"]["APIKeyHeader"]["name"] == "X-API-Key"
    listado = esquema["paths"]["/v1/noticias"]["get"]["responses"]
    assert listado["200"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/ListaNoticias"
    )
    assert {"304", "400", "401", "403", "422", "429"} <= set(listado)


async def test_docs_desactivables(crear_cliente: CrearCliente) -> None:
    async with crear_cliente(docs_enabled=False) as cliente:
        assert (await cliente.get("/openapi.json")).status_code == 404
        assert (await cliente.get("/docs")).status_code == 404


def test_formato_json_de_logs() -> None:
    registro = logging.makeLogRecord(
        {"name": "prueba", "levelname": "INFO", "msg": "hola %s", "args": ("mundo",)}
    )
    registro.ruta = "/v1/noticias"
    token = request_id_actual.set("rid-9")
    try:
        linea = json.loads(FormateadorJSON().format(registro))
    finally:
        request_id_actual.reset(token)
    assert linea["message"] == "hola mundo"
    assert linea["level"] == "INFO"
    assert linea["request_id"] == "rid-9"
    assert linea["ruta"] == "/v1/noticias"


async def test_log_de_acceso(cliente: httpx.AsyncClient, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="app.acceso")
    await cliente.get("/health", headers={"X-Request-ID": "rid-log"})
    registro = next(r for r in caplog.records if r.name == "app.acceso")
    assert registro.__dict__["ruta"] == "/health"
    assert registro.__dict__["estado"] == 200
    assert "duracion_ms" in registro.__dict__
