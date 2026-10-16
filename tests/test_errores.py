import httpx


async def test_request_id_generado_o_propagado(cliente: httpx.AsyncClient) -> None:
    propio = await cliente.get("/health", headers={"X-Request-ID": "abc-123"})
    generado = await cliente.get("/health")
    invalido = await cliente.get("/health", headers={"X-Request-ID": "no valido!"})
    assert propio.headers["x-request-id"] == "abc-123"
    assert len(generado.headers["x-request-id"]) == 32
    assert invalido.headers["x-request-id"] != "no valido!"


async def test_ruta_inexistente_con_formato_uniforme(cliente: httpx.AsyncClient) -> None:
    respuesta = await cliente.get("/no-existe", headers={"X-Request-ID": "rid-1"})
    assert respuesta.status_code == 404
    assert respuesta.json() == {
        "error": {
            "codigo": "no_encontrado",
            "mensaje": "Recurso no encontrado.",
            "request_id": "rid-1",
        }
    }


async def test_metodo_no_permitido(cliente: httpx.AsyncClient) -> None:
    respuesta = await cliente.post("/health")
    assert respuesta.status_code == 405
    assert respuesta.json()["error"]["codigo"] == "metodo_no_permitido"
    assert respuesta.headers["allow"] == "GET"
