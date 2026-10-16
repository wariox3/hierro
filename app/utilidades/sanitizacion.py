"""Sanitización del HTML de `contenido` con nh3 (lista blanca)."""

import nh3

ETIQUETAS_PERMITIDAS = frozenset(
    {
        "a", "abbr", "b", "blockquote", "br", "caption", "cite", "code", "em", "figcaption",
        "figure", "h2", "h3", "h4", "h5", "h6", "hr", "i", "img", "li", "ol", "p", "pre", "q",
        "s", "small", "span", "strong", "sub", "sup", "table", "tbody", "td", "tfoot", "th",
        "thead", "tr", "u", "ul",
    }
)  # fmt: skip

ATRIBUTOS_PERMITIDOS: dict[str, set[str]] = {
    "a": {"href", "title"},
    "abbr": {"title"},
    "img": {"src", "alt", "title", "width", "height"},
    "td": {"colspan", "rowspan"},
    "th": {"colspan", "rowspan", "scope"},
}

ESQUEMAS_URL_PERMITIDOS = frozenset({"http", "https", "mailto"})


def sanitizar_html(html: str) -> str:
    """Elimina scripts, estilos, eventos `on*` y URLs peligrosas (p. ej. `javascript:`)."""
    return nh3.clean(
        html,
        tags=set(ETIQUETAS_PERMITIDAS),
        attributes=ATRIBUTOS_PERMITIDOS,
        url_schemes=set(ESQUEMAS_URL_PERMITIDOS),
        link_rel="noopener noreferrer nofollow",
    )
