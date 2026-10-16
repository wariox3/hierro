from tests.conftest import CrearCliente, Datos

URL = "/v1/noticias"


async def test_excede_el_limite_429(crear_cliente: CrearCliente, datos: Datos) -> None:
    _, key = await datos.api_key("a")
    _, otra_key = await datos.api_key("b")
    async with crear_cliente(rate_limit_requests=3, rate_limit_window=60) as cliente:
        estados = [
            (await cliente.get(URL, headers={"X-API-Key": key})).status_code for _ in range(4)
        ]
        bloqueada = await cliente.get(URL, headers={"X-API-Key": key})
        otra = await cliente.get(URL, headers={"X-API-Key": otra_key})

    assert estados == [200, 200, 200, 429]
    assert bloqueada.json()["error"]["codigo"] == "limite_excedido"
    assert 1 <= int(bloqueada.headers["retry-after"]) <= 60
    assert bloqueada.headers["x-ratelimit-limit"] == "3"
    # El límite es por API key: la otra key no se ve afectada.
    assert otra.status_code == 200


async def test_sin_redis_no_limita(crear_cliente: CrearCliente, datos: Datos) -> None:
    _, key = await datos.api_key()
    async with crear_cliente(rate_limit_requests=1, redis_url="redis://localhost:1/0") as cliente:
        estados = {
            (await cliente.get(URL, headers={"X-API-Key": key})).status_code for _ in range(3)
        }
    assert estados == {200}
