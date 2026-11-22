import sqlite3
from collections.abc import Iterator
from pathlib import Path

from fastapi import Request


def conectar(ruta: Path) -> sqlite3.Connection:
    """Abre una conexión. Cada conexión tiene un único dueño a la vez.

    `check_same_thread=False` es seguro por ese patrón: FastAPI puede crear la dependencia
    en un hilo del pool y cerrarla en otro, pero la conexión nunca se usa desde dos hilos
    a la vez. Una petición crea su propia conexión y la cierra al terminar.
    """
    ruta.parent.mkdir(parents=True, exist_ok=True)
    conexion = sqlite3.connect(ruta, timeout=30, check_same_thread=False)
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
