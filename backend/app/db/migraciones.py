import sqlite3
from pathlib import Path

DIRECTORIO_MIGRACIONES = Path(__file__).resolve().parent / "migraciones"


def aplicar_migraciones(conexion: sqlite3.Connection) -> int:
    """Aplica los archivos NNNN_nombre.sql pendientes, en orden. Devuelve la versión final.

    La versión se guarda en PRAGMA user_version. Cada migración corre en una transacción
    junto con su actualización de versión, así que un fallo no deja el esquema a medias.
    """
    version_actual = conexion.execute("PRAGMA user_version").fetchone()[0]

    for ruta in sorted(DIRECTORIO_MIGRACIONES.glob("*.sql")):
        numero = int(ruta.name.split("_", 1)[0])
        if numero <= version_actual:
            continue

        sql = ruta.read_text(encoding="utf-8")
        try:
            conexion.executescript(f"BEGIN;\n{sql}\nPRAGMA user_version = {numero};\nCOMMIT;")
        except sqlite3.Error:
            if conexion.in_transaction:
                conexion.execute("ROLLBACK")
            raise
        version_actual = numero

    return version_actual
