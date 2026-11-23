import sqlite3
from typing import Any

COLUMNAS = (
    "id, proyecto_id, nombre, ruta_original, tamano_bytes, duracion_segundos, "
    "ancho, alto, fps, codec_video, codec_audio, formato, creado"
)


def insertar(conexion: sqlite3.Connection, datos: dict[str, Any]) -> int:
    cursor = conexion.execute(
        """
        INSERT INTO videos (
            proyecto_id, nombre, ruta_original, tamano_bytes, duracion_segundos,
            ancho, alto, fps, codec_video, codec_audio, formato
        ) VALUES (
            :proyecto_id, :nombre, :ruta_original, :tamano_bytes, :duracion_segundos,
            :ancho, :alto, :fps, :codec_video, :codec_audio, :formato
        )
        """,
        datos,
    )
    conexion.commit()
    return int(cursor.lastrowid)


def listar_por_proyecto(conexion: sqlite3.Connection, proyecto_id: int) -> list[sqlite3.Row]:
    return conexion.execute(
        f"SELECT {COLUMNAS} FROM videos WHERE proyecto_id = ? ORDER BY id",
        (proyecto_id,),
    ).fetchall()


def obtener(conexion: sqlite3.Connection, video_id: int) -> sqlite3.Row | None:
    return conexion.execute(
        f"SELECT {COLUMNAS} FROM videos WHERE id = ?", (video_id,)
    ).fetchone()


def ids(conexion: sqlite3.Connection) -> set[int]:
    return {int(fila["id"]) for fila in conexion.execute("SELECT id FROM videos").fetchall()}


def contar_por_proyecto(conexion: sqlite3.Connection, proyecto_id: int) -> int:
    fila = conexion.execute(
        "SELECT COUNT(*) AS cantidad FROM videos WHERE proyecto_id = ?", (proyecto_id,)
    ).fetchone()
    return int(fila["cantidad"])


def contar_por_proyectos(conexion: sqlite3.Connection) -> list[sqlite3.Row]:
    """Una fila por proyecto que tenga videos. Los proyectos sin videos no aparecen."""
    return conexion.execute(
        "SELECT proyecto_id, COUNT(*) AS cantidad FROM videos GROUP BY proyecto_id"
    ).fetchall()


def eliminar(conexion: sqlite3.Connection, video_id: int) -> bool:
    """Borra solo la fila de SQLite. No hace commit: la transacción la cierra quien llama.

    El archivo original no se toca.
    """
    cursor = conexion.execute("DELETE FROM videos WHERE id = ?", (video_id,))
    return cursor.rowcount > 0
