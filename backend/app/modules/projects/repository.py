import sqlite3


def insertar(conexion: sqlite3.Connection, nombre: str) -> int:
    cursor = conexion.execute("INSERT INTO proyectos (nombre) VALUES (?)", (nombre,))
    conexion.commit()
    return int(cursor.lastrowid)


def listar(conexion: sqlite3.Connection) -> list[sqlite3.Row]:
    return conexion.execute("SELECT id, nombre, creado FROM proyectos ORDER BY id").fetchall()


def obtener(conexion: sqlite3.Connection, proyecto_id: int) -> sqlite3.Row | None:
    return conexion.execute(
        "SELECT id, nombre, creado FROM proyectos WHERE id = ?", (proyecto_id,)
    ).fetchone()
