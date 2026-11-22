import hmac
import os
import secrets
from pathlib import Path


def generar_token() -> str:
    return secrets.token_urlsafe(32)


def escribir_token(ruta: Path, token: str) -> None:
    """Escribe el token en un temporal con permisos restringidos y lo renombra de forma atómica."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = ruta.with_name(ruta.name + ".tmp")
    descriptor = os.open(temporal, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as archivo:
        archivo.write(token)
    os.replace(temporal, ruta)


def token_valido(recibido: str | None, esperado: str) -> bool:
    if not recibido:
        return False
    return hmac.compare_digest(recibido.encode("utf-8"), esperado.encode("utf-8"))
