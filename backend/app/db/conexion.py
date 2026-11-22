import sqlite3
from collections.abc import Iterator
from pathlib import Path

from fastapi import Request


def conectar(ruta: Path) -> sqlite3.Connection:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    conexion = sqlite3.connect(ruta, timeout=30)
    conexion.row_factory = sqlite3.Row
    conexion.execute("PRAGMA foreign_keys = ON")
    conexion.execute("PRAGMA journal_mode = WAL")
    return conexion


def obtener_conexion(request: Request) -> Iterator[sqlite3.Connection]:
    """Dependencia de FastAPI: una conexión por petición, cerrada al terminar."""
    conexion = conectar(request.app.state.configuracion.ruta_base_datos)
    try:
        yield conexion
    finally:
        conexion.close()
