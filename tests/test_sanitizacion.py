import httpx
import pytest

from app.utilidades.sanitizacion import sanitizar_html
from tests.conftest import Datos


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("<p>Hola <strong>mundo</strong></p>", "<p>Hola <strong>mundo</strong></p>"),
        ("<p>a</p><script>alert(1)</script>", "<p>a</p>"),
        ("<style>body{}</style><p>a</p>", "<p>a</p>"),
        ('<p onclick="robar()">a</p>', "<p>a</p>"),
        ('<a href="javascript:alert(1)">x</a>', '<a rel="noopener noreferrer nofollow">x</a>'),
        (
            '<a href="https://ejemplo.com" target="_blank">x</a>',
            '<a href="https://ejemplo.com" rel="noopener noreferrer nofollow">x</a>',
        ),
        ('<img src="https://cdn.ejemplo.com/a.jpg" alt="A" onerror="x()">',
         '<img src="https://cdn.ejemplo.com/a.jpg" alt="A">'),
        ("<iframe src='https://malo.com'></iframe><p>a</p>", "<p>a</p>"),
        ('<p style="color:red">a</p>', "<p>a</p>"),
        ("<p>a<!-- comentario --></p>", "<p>a</p>"),
    ],
)  # fmt: skip
def test_sanitizar_html(entrada: str, esperado: str) -> None:
    assert sanitizar_html(entrada) == esperado


async def test_listado_devuelve_html_sanitizado(cliente: httpx.AsyncClient, datos: Datos) -> None:
    _, key = await datos.api_key()
    await datos.noticia(contenido='<p onclick="x()">Hola</p><script>alert(1)</script>')
    respuesta = await cliente.get("/noticias/v1/lista", headers={"X-API-Key": key})
    assert respuesta.json()["datos"][0]["contenido"] == "<p>Hola</p>"
