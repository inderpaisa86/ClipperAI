"""Inicio del análisis visual de un video. Lo llama código del servidor, no un cliente HTTP."""
import sqlite3

from app.core.errores import Conflicto, NoEncontrado, SolicitudInvalida
from app.jobs import service as trabajos
from app.modules.analisis import service as analisis
from app.modules.vision import analizador
from app.modules.vision.parametros import PARAMETROS_POR_DEFECTO
from app.modules.videos import service as videos
from app.plugins.registro import REGISTRO

TIPO_TRABAJO = "analisis_video"
TIPO_SEGMENTO_FOTOGRAMAS = "fotogramas"
TIPO_SEGMENTO_CIERRE = "cierre"


def planificar_segmentos(duracion_ms: int, duracion_segmento_ms: int) -> list[tuple[str, int, int, int]]:
    """Segmentos de trabajo como (tipo, indice, inicio_ms, fin_ms).

    Los segmentos de fotogramas cubren el video en bloques de `duracion_segmento_ms`. El segmento de cierre va
    al final y marca el análisis como completado, en la misma transacción que su última confirmación.
    """
    segmentos: list[tuple[str, int, int, int]] = []
    inicio = 0
    indice = 0
    while inicio < duracion_ms:
        fin = min(inicio + duracion_segmento_ms, duracion_ms)
        segmentos.append((TIPO_SEGMENTO_FOTOGRAMAS, indice, inicio, fin))
        inicio = fin
        indice += 1
    segmentos.append((TIPO_SEGMENTO_CIERRE, 0, 0, duracion_ms))
    return segmentos


def iniciar_analisis(conexion: sqlite3.Connection, video_id: int) -> int:
    """Crea el trabajo de análisis visual de un video y devuelve su id.

    El análisis queda en curso dentro de la misma transacción que crea el trabajo. Si el video ya tiene un
    análisis visual completo con esta versión, lanza Conflicto.
    """
    datos = videos.datos_para_analisis(conexion, video_id)
    if not datos.tiene_video:
        raise SolicitudInvalida("El video no tiene pista de vídeo.")
    if datos.duracion_ms is None or datos.duracion_ms <= 0:
        raise SolicitudInvalida("No se conoce la duración del video.")
    if datos.ancho is None or datos.alto is None:
        raise SolicitudInvalida("No se conocen las dimensiones del video.")
    if not REGISTRO.existe(analizador.IDENTIFICADOR):
        raise NoEncontrado("El analizador no está disponible.")
    if analisis.estado_completado_con_version(
        conexion, video_id, analizador.IDENTIFICADOR, analizador.VERSION
    ):
        raise Conflicto("El análisis visual de este video ya está completo con esta versión.")
    return trabajos.crear(
        conexion,
        TIPO_TRABAJO,
        {"video_id": video_id, "analizador": analizador.IDENTIFICADOR},
        planificar_segmentos(datos.duracion_ms, PARAMETROS_POR_DEFECTO.duracion_segmento_ms),
        al_insertar=lambda conexion_trabajo, trabajo_id: analisis.reservar_para_trabajo(
            conexion_trabajo, video_id, analizador.IDENTIFICADOR, analizador.VERSION, trabajo_id
        ),
    )
