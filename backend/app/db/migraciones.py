import sqlite3
from collections.abc import Iterator
from pathlib import Path

DIRECTORIO_MIGRACIONES = Path(__file__).resolve().parent / "migraciones"

# Una migración que reconstruye una tabla referenciada por otras declara esta marca en su primera línea.
# El runner desactiva las claves externas antes de abrir la transacción, verifica la base antes de confirmar
# y restaura el estado anterior de `foreign_keys` al terminar, haya éxito o fallo.
MARCA_SIN_CLAVES_EXTERNAS = "-- requiere: claves_externas_desactivadas"


def _sentencias(sql: str) -> Iterator[str]:
    """Separa un script en sentencias completas. sqlite3.complete_statement ignora los comentarios."""
    acumulado = ""
    for linea in sql.splitlines(keepends=True):
        acumulado += linea
        if sqlite3.complete_statement(acumulado):
            if acumulado.strip():
                yield acumulado.strip()
            acumulado = ""
    if acumulado.strip():
        yield acumulado.strip()


def _verificar_base(conexion: sqlite3.Connection) -> None:
    """Falla si hay claves externas rotas o la base no pasa la comprobación de integridad."""
    violaciones = conexion.execute("PRAGMA foreign_key_check").fetchall()
    if violaciones:
        raise sqlite3.IntegrityError(f"La migración deja {len(violaciones)} referencias externas rotas.")
    integridad = conexion.execute("PRAGMA integrity_check").fetchone()[0]
    if integridad != "ok":
        raise sqlite3.DatabaseError(f"La migración deja la base con errores de integridad: {integridad}")


def _aplicar_sin_claves_externas(conexion: sqlite3.Connection, sql: str, numero: int) -> None:
    previas = conexion.execute("PRAGMA foreign_keys").fetchone()[0]
    # Solo tiene efecto fuera de una transacción, así que va antes de BEGIN.
    conexion.execute("PRAGMA foreign_keys = OFF")
    try:
        conexion.execute("BEGIN IMMEDIATE")
        for sentencia in _sentencias(sql):
            conexion.execute(sentencia)
        _verificar_base(conexion)
        conexion.execute(f"PRAGMA user_version = {numero}")
        conexion.execute("COMMIT")
    except BaseException:
        if conexion.in_transaction:
            conexion.execute("ROLLBACK")
        raise
    finally:
        conexion.execute(f"PRAGMA foreign_keys = {'ON' if previas else 'OFF'}")


def aplicar_migraciones(
    conexion: sqlite3.Connection,
    hasta: int | None = None,
    directorio: Path = DIRECTORIO_MIGRACIONES,
) -> int:
    """Aplica los archivos NNNN_nombre.sql pendientes, en orden. Devuelve la versión final.

    La versión se guarda en PRAGMA user_version. Cada migración corre en una transacción junto con su
    actualización de versión, así que un fallo no deja el esquema a medias. `hasta` limita la versión
    aplicada; lo usan las pruebas para preparar una base en una versión anterior.
    """
    version_actual = conexion.execute("PRAGMA user_version").fetchone()[0]
    for ruta in sorted(directorio.glob("*.sql")):
        numero = int(ruta.name.split("_", 1)[0])
        if numero <= version_actual:
            continue
        if hasta is not None and numero > hasta:
            break
        sql = ruta.read_text(encoding="utf-8")
        if sql.startswith(MARCA_SIN_CLAVES_EXTERNAS):
            _aplicar_sin_claves_externas(conexion, sql, numero)
        else:
            try:
                conexion.executescript(f"BEGIN;\n{sql}\nPRAGMA user_version = {numero};\nCOMMIT;")
            except sqlite3.Error:
                if conexion.in_transaction:
                    conexion.execute("ROLLBACK")
                raise
        version_actual = numero
    return version_actual
