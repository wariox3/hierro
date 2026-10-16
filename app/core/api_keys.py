"""Generación y hash de API keys. En la base solo se guardan el hash y el prefijo."""

import hashlib
import secrets
from dataclasses import dataclass

PREFIJO_KEY = "nk_"
LARGO_PREFIJO_VISIBLE = 12


@dataclass(frozen=True)
class ApiKeyGenerada:
    key: str
    hash: str
    prefijo: str


def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def generar_api_key() -> ApiKeyGenerada:
    key = PREFIJO_KEY + secrets.token_urlsafe(32)
    return ApiKeyGenerada(key=key, hash=hash_api_key(key), prefijo=key[:LARGO_PREFIJO_VISIBLE])
