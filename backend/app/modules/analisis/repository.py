"""Acceso a las tablas analisis, senales y fotogramas. Ninguna función de este archivo hace commit."""

import sqlite3
from collections.abc import Iterable
from typing import Any

COLUMNAS_ANALISIS = (
    "id, video_id, analizador, version_analizador, estado, error, creado, actualizado"
)


def obtener_por_id(conexion: sqlite3.Connection, analisis_id: int) -> sqlite3.Row | None:
    return conexion.execute(
        f"SELECT {COLUMNAS_ANALISIS}, trabajo_id FROM analisis WHERE id = ?", (analisis_id,)
    ).fetchone()


def obtener_analisis(
    conexion: sqlite3.Connection, video_id: int, analizador: str
) -> sqlite3.Row | None:
    return conexion.execute(
        f"SELECT {COLUMNAS_ANALISIS}, trabajo_id FROM analisis WHERE video_id = ? AND analizador = ?",
        (video_id, analizador),
    ).fetchone()


def listar_analisis_de_video(conexion: sqlite3.Connection, video_id: int) -> list[sqlite3.Row]:
    return conexion.execute(
        f"SELECT {COLUMNAS_ANALISIS}, trabajo_id FROM analisis WHERE video_id = ? ORDER BY analizador",
        (video_id,),
    ).fetchall()


def insertar_analisis(
    conexion: sqlite3.Connection, video_id: int, analizador: str, version: str, ahora: str
) -> int:
    cursor = conexion.execute(
        "INSERT INTO analisis (video_id, analizador, version_analizador, estado, creado, actualizado) "
        "VALUES (?, ?, ?, 'pendiente', ?, ?)",
        (video_id, analizador, version, ahora, ahora),
    )
    return int(cursor.lastrowid)


def reiniciar_analisis(
    conexion: sqlite3.Connection, analisis_id: int, version: str, ahora: str
) -> int:
    """Pasa el análisis a pendiente con una versión nueva. No borra resultados: eso lo decide el servicio."""
    cursor = conexion.execute(
        "UPDATE analisis SET version_analizador = ?, estado = 'pendiente', error = NULL, "
        "trabajo_id = NULL, actualizado = ? WHERE id = ?",
        (version, ahora, analisis_id),
    )
    return cursor.rowcount


def cambiar_estado(
    conexion: sqlite3.Connection,
    analisis_id: int,
    estado: str,
    trabajo_id: int | None,
    error: str | None,
    ahora: str,
) -> int:
    cursor = conexion.execute(
        "UPDATE analisis SET estado = ?, trabajo_id = ?, error = ?, actualizado = ? WHERE id = ?",
        (estado, trabajo_id, error, ahora, analisis_id),
    )
    return cursor.rowcount


def borrar_resultados(conexion: sqlite3.Connection, analisis_id: int) -> None:
    conexion.execute("DELETE FROM senales WHERE analisis_id = ?", (analisis_id,))
    conexion.execute("DELETE FROM fotogramas WHERE analisis_id = ?", (analisis_id,))


def insertar_senales(
    conexion: sqlite3.Connection, filas: Iterable[tuple[Any, ...]]
) -> None:
    """Una señal repetida (mismo tipo e intervalo) se ignora, así reprocesar un segmento es seguro."""
    conexion.executemany(
        "INSERT OR IGNORE INTO senales "
        "(analisis_id, tipo, inicio_ms, fin_ms, valor, confianza) VALUES (?, ?, ?, ?, ?, ?)",
        filas,
    )


def insertar_fotogramas(
    conexion: sqlite3.Connection, filas: Iterable[tuple[Any, ...]]
) -> None:
    conexion.executemany(
        "INSERT OR IGNORE INTO fotogramas (analisis_id, tiempo_ms, ruta_relativa, creado) "
        "VALUES (?, ?, ?, ?)",
        filas,
    )


def listar_senales(
    conexion: sqlite3.Connection,
    analisis_id: int,
    inicio_ms: int | None,
    fin_ms: int | None,
    limite: int,
    tipo: str | None = None,
) -> list[sqlite3.Row]:
    """Señales que se solapan con [inicio_ms, fin_ms], de un tipo si se indica."""
    return conexion.execute(
        "SELECT tipo, inicio_ms, fin_ms, valor, confianza FROM senales "
        "WHERE analisis_id = ? "
        "AND (? IS NULL OR fin_ms >= ?) "
        "AND (? IS NULL OR inicio_ms <= ?) "
        "AND (? IS NULL OR tipo = ?) "
        "ORDER BY inicio_ms, fin_ms, tipo LIMIT ?",
        (analisis_id, inicio_ms, inicio_ms, fin_ms, fin_ms, tipo, tipo, limite),
    ).fetchall()


def listar_fotogramas(
    conexion: sqlite3.Connection, analisis_id: int, limite: int
) -> list[sqlite3.Row]:
    return conexion.execute(
        "SELECT tiempo_ms FROM fotogramas WHERE analisis_id = ? ORDER BY tiempo_ms LIMIT ?",
        (analisis_id, limite),
    ).fetchall()


def obtener_fotograma(
    conexion: sqlite3.Connection, analisis_id: int, tiempo_ms: int
) -> sqlite3.Row | None:
    return conexion.execute(
        "SELECT ruta_relativa FROM fotogramas WHERE analisis_id = ? AND tiempo_ms = ?",
        (analisis_id, tiempo_ms),
    ).fetchone()


def rutas_fotogramas_de_video(conexion: sqlite3.Connection, video_id: int) -> set[str]:
    filas = conexion.execute(
        "SELECT f.ruta_relativa FROM fotogramas f JOIN analisis a ON a.id = f.analisis_id "
        "WHERE a.video_id = ?",
        (video_id,),
    ).fetchall()
    return {fila["ruta_relativa"] for fila in filas}
def ultimo_fin_senal(
    conexion: sqlite3.Connection, analisis_id: int, tipo: str, antes_de_ms: int
) -> int | None:
    """Fin más tardío de una señal del tipo que termina antes del tiempo indicado."""
    fila = conexion.execute(
        "SELECT MAX(fin_ms) AS fin FROM senales WHERE analisis_id = ? AND tipo = ? AND fin_ms < ?",
        (analisis_id, tipo, antes_de_ms),
    ).fetchone()
    return None if fila["fin"] is None else int(fila["fin"])
def ultimo_tiempo_fotograma(
    conexion: sqlite3.Connection, analisis_id: int, antes_de_ms: int
) -> int | None:
    fila = conexion.execute(
        "SELECT MAX(tiempo_ms) AS tiempo FROM fotogramas WHERE analisis_id = ? AND tiempo_ms < ?",
        (analisis_id, antes_de_ms),
    ).fetchone()
    return None if fila["tiempo"] is None else int(fila["tiempo"])
def senales_por_tipo(
    conexion: sqlite3.Connection, analisis_id: int, tipo: str
) -> list[sqlite3.Row]:
    return conexion.execute(
        "SELECT inicio_ms, fin_ms, valor, confianza FROM senales "
        "WHERE analisis_id = ? AND tipo = ? ORDER BY inicio_ms, fin_ms",
        (analisis_id, tipo),
    ).fetchall()
def ids_en_curso_de_trabajo(conexion: sqlite3.Connection, trabajo_id: int) -> list[int]:
    return [int(fila["id"]) for fila in conexion.execute(
        "SELECT id FROM analisis WHERE trabajo_id = ? AND estado = 'en_curso'", (trabajo_id,)
    ).fetchall()]
def trabajos_en_curso_de_video(conexion: sqlite3.Connection, video_id: int) -> list[sqlite3.Row]:
    """Trabajo asociado a cada análisis que está en curso. El trabajo puede haber terminado ya."""
    return conexion.execute(
        "SELECT trabajo_id FROM analisis WHERE video_id = ? AND estado = 'en_curso'",
        (video_id,),
    ).fetchall()
def borrar_analisis_de_video(conexion: sqlite3.Connection, video_id: int) -> int:
    """Borra los análisis del video. Sus señales y fotogramas se borran en cascada."""
    cursor = conexion.execute("DELETE FROM analisis WHERE video_id = ?", (video_id,))
    return cursor.rowcount
