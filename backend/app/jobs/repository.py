import sqlite3
from collections.abc import Iterable


def insertar_trabajo(conexion: sqlite3.Connection, tipo: str, payload_json: str, ahora: str) -> int:
    cursor = conexion.execute(
        "INSERT INTO trabajos (tipo, estado, payload_json, creado, actualizado) "
        "VALUES (?, 'en_cola', ?, ?, ?)",
        (tipo, payload_json, ahora, ahora),
    )
    return int(cursor.lastrowid)


def insertar_segmentos(
    conexion: sqlite3.Connection,
    trabajo_id: int,
    segmentos: Iterable[tuple[str, int, int, int]],
    ahora: str,
) -> None:
    conexion.executemany(
        "INSERT INTO segmentos_trabajo "
        "(trabajo_id, tipo_analisis, indice, inicio_ms, fin_ms, estado, actualizado) "
        "VALUES (?, ?, ?, ?, ?, 'pendiente', ?)",
        [(trabajo_id, tipo, indice, inicio, fin, ahora) for tipo, indice, inicio, fin in segmentos],
    )


def obtener(conexion: sqlite3.Connection, trabajo_id: int) -> sqlite3.Row | None:
    return conexion.execute("SELECT * FROM trabajos WHERE id = ?", (trabajo_id,)).fetchone()


def obtener_ejecucion(
    conexion: sqlite3.Connection, trabajo_id: int, token: str
) -> sqlite3.Row | None:
    """Fila solo si el trabajo sigue ejecutándose con ese token. Es la comprobación de propiedad."""
    return conexion.execute(
        "SELECT * FROM trabajos WHERE id = ? AND estado = 'ejecutando' AND claim_token = ?",
        (trabajo_id, token),
    ).fetchone()


def hay_ejecucion(conexion: sqlite3.Connection) -> bool:
    return conexion.execute(
        "SELECT 1 FROM trabajos WHERE estado = 'ejecutando' LIMIT 1"
    ).fetchone() is not None


def primer_en_cola(conexion: sqlite3.Connection) -> int | None:
    fila = conexion.execute(
        "SELECT id FROM trabajos WHERE estado = 'en_cola' ORDER BY id LIMIT 1"
    ).fetchone()
    return None if fila is None else int(fila["id"])


def reclamar(conexion: sqlite3.Connection, trabajo_id: int, token: str, ahora: str) -> int:
    """Pasa a ejecutando solo si sigue en cola y no hay otro trabajo ejecutándose."""
    cursor = conexion.execute(
        "UPDATE trabajos SET estado = 'ejecutando', claim_token = ?, intentos = intentos + 1, "
        "pid = NULL, identidad_proceso = NULL, latido = ?, actualizado = ? "
        "WHERE id = ? AND estado = 'en_cola' "
        "AND NOT EXISTS (SELECT 1 FROM trabajos WHERE estado = 'ejecutando')",
        (token, ahora, ahora, trabajo_id),
    )
    return cursor.rowcount


def registrar_proceso(
    conexion: sqlite3.Connection,
    trabajo_id: int,
    token: str,
    pid: int,
    identidad: str,
    ahora: str,
) -> int:
    cursor = conexion.execute(
        "UPDATE trabajos SET pid = ?, identidad_proceso = ?, latido = ?, actualizado = ? "
        "WHERE id = ? AND claim_token = ? AND estado = 'ejecutando'",
        (pid, identidad, ahora, ahora, trabajo_id, token),
    )
    return cursor.rowcount


def actualizar_latido(
    conexion: sqlite3.Connection,
    trabajo_id: int,
    token: str,
    progreso: int | None,
    ahora: str,
) -> int:
    cursor = conexion.execute(
        "UPDATE trabajos SET latido = ?, actualizado = ?, progreso = COALESCE(?, progreso) "
        "WHERE id = ? AND claim_token = ? AND estado = 'ejecutando'",
        (ahora, ahora, progreso, trabajo_id, token),
    )
    return cursor.rowcount


def marcar_cancelacion_en_ejecucion(conexion: sqlite3.Connection, trabajo_id: int, ahora: str) -> int:
    cursor = conexion.execute(
        "UPDATE trabajos SET cancelacion_solicitada = 1, actualizado = ? "
        "WHERE id = ? AND estado = 'ejecutando'",
        (ahora, trabajo_id),
    )
    return cursor.rowcount


def cancelar_en_cola(conexion: sqlite3.Connection, trabajo_id: int, ahora: str) -> int:
    cursor = conexion.execute(
        "UPDATE trabajos SET estado = 'cancelado', cancelacion_solicitada = 1, actualizado = ? "
        "WHERE id = ? AND estado = 'en_cola'",
        (ahora, trabajo_id),
    )
    return cursor.rowcount


def terminar(
    conexion: sqlite3.Connection,
    trabajo_id: int,
    token: str,
    estado: str,
    error: str | None,
    exigir_sin_cancelacion: bool,
    ahora: str,
) -> int:
    """Estado final. Con exigir_sin_cancelacion, un trabajo cancelado no puede completarse."""
    cursor = conexion.execute(
        "UPDATE trabajos SET estado = ?, claim_token = NULL, pid = NULL, identidad_proceso = NULL, "
        "error = ?, progreso = CASE WHEN ? = 'completado' THEN 100 ELSE progreso END, actualizado = ? "
        "WHERE id = ? AND claim_token = ? AND estado = 'ejecutando' "
        "AND (? = 0 OR cancelacion_solicitada = 0)",
        (estado, error, estado, ahora, trabajo_id, token, 1 if exigir_sin_cancelacion else 0),
    )
    return cursor.rowcount


def reencolar(conexion: sqlite3.Connection, trabajo_id: int, token: str, ahora: str) -> int:
    cursor = conexion.execute(
        "UPDATE trabajos SET estado = 'en_cola', claim_token = NULL, pid = NULL, "
        "identidad_proceso = NULL, progreso = 0, latido = NULL, actualizado = ? "
        "WHERE id = ? AND claim_token = ? AND estado = 'ejecutando'",
        (ahora, trabajo_id, token),
    )
    return cursor.rowcount


def reencolar_por_parada(conexion: sqlite3.Connection, trabajo_id: int, token: str, ahora: str) -> int:
    """Devuelve a cola tras una parada ordenada. El intento reclamado no cuenta, así que se revierte."""
    cursor = conexion.execute(
        "UPDATE trabajos SET estado = 'en_cola', claim_token = NULL, pid = NULL, "
        "identidad_proceso = NULL, progreso = 0, latido = NULL, "
        "intentos = MAX(intentos - 1, 0), actualizado = ? "
        "WHERE id = ? AND claim_token = ? AND estado = 'ejecutando'",
        (ahora, trabajo_id, token),
    )
    return cursor.rowcount


def cambiar_segmentos_procesando(
    conexion: sqlite3.Connection, trabajo_id: int, nuevo_estado: str, ahora: str
) -> None:
    conexion.execute(
        "UPDATE segmentos_trabajo SET estado = ?, actualizado = ? "
        "WHERE trabajo_id = ? AND estado = 'procesando'",
        (nuevo_estado, ahora, trabajo_id),
    )


def listar_ejecucion(conexion: sqlite3.Connection) -> list[sqlite3.Row]:
    return conexion.execute(
        "SELECT id, claim_token, pid, identidad_proceso, latido, cancelacion_solicitada, intentos "
        "FROM trabajos WHERE estado = 'ejecutando' ORDER BY id"
    ).fetchall()


def marcar_segmento_procesando(
    conexion: sqlite3.Connection, trabajo_id: int, tipo: str, indice: int, ahora: str
) -> int:
    cursor = conexion.execute(
        "UPDATE segmentos_trabajo SET estado = 'procesando', actualizado = ? "
        "WHERE trabajo_id = ? AND tipo_analisis = ? AND indice = ? AND estado = 'pendiente'",
        (ahora, trabajo_id, tipo, indice),
    )
    return cursor.rowcount


def confirmar_segmento(
    conexion: sqlite3.Connection,
    trabajo_id: int,
    tipo: str,
    indice: int,
    salida_ruta: str | None,
    salida_tamano: int | None,
    version_analizador: str | None,
    ahora: str,
) -> int:
    cursor = conexion.execute(
        "UPDATE segmentos_trabajo SET estado = 'completado', salida_ruta = ?, salida_tamano = ?, "
        "version_analizador = ?, actualizado = ? "
        "WHERE trabajo_id = ? AND tipo_analisis = ? AND indice = ? AND estado = 'procesando'",
        (salida_ruta, salida_tamano, version_analizador, ahora, trabajo_id, tipo, indice),
    )
    return cursor.rowcount


def obtener_segmento(
    conexion: sqlite3.Connection, trabajo_id: int, tipo: str, indice: int
) -> sqlite3.Row | None:
    return conexion.execute(
        "SELECT * FROM segmentos_trabajo WHERE trabajo_id = ? AND tipo_analisis = ? AND indice = ?",
        (trabajo_id, tipo, indice),
    ).fetchone()
