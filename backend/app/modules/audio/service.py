"""Inicio del análisis de audio de un video. Lo llama código del servidor, no un cliente HTTP."""

import sqlite3

from app.core.errores import Conflicto, NoEncontrado, SolicitudInvalida
from app.jobs import service as trabajos
from app.modules.analisis import service as analisis
from app.modules.audio import analizador
from app.modules.videos import service as videos
from app.plugins.registro import REGISTRO

TIPO_TRABAJO = "analisis_audio"
DURACION_SEGMENTO_MS = 60_000  # Múltiplo de 200 ms: las ventanas de energía quedan alineadas entre segmentos.
TIPO_SEGMENTO_ENERGIA = "energia"
TIPO_SEGMENTO_CONSOLIDACION = "consolidacion"


def planificar_segmentos(duracion_ms: int) -> list[tuple[str, int, int, int]]:
    """Segmentos de trabajo como (tipo, indice, inicio_ms, fin_ms).

    Los segmentos de energía cubren el video en bloques de 60 s. El segmento de consolidación va al final
    y abarca todo el video, porque los silencios dependen de la serie completa.
    """
    segmentos: list[tuple[str, int, int, int]] = []
    inicio = 0
    indice = 0
    while inicio < duracion_ms:
        fin = min(inicio + DURACION_SEGMENTO_MS, duracion_ms)
        segmentos.append((TIPO_SEGMENTO_ENERGIA, indice, inicio, fin))
        inicio = fin
        indice += 1
    segmentos.append((TIPO_SEGMENTO_CONSOLIDACION, 0, 0, duracion_ms))
    return segmentos


def iniciar_analisis(conexion: sqlite3.Connection, video_id: int) -> int:
    """Crea el trabajo de análisis de audio de un video y devuelve su id.

    El análisis queda en curso dentro de la misma transacción que crea el trabajo. Si el video ya tiene un
    análisis de audio completo con esta versión, lanza Conflicto.
    """
    datos = videos.datos_para_analisis(conexion, video_id)
    if not datos.tiene_audio:
        raise SolicitudInvalida("El video no tiene pista de audio.")
    if datos.duracion_ms is None or datos.duracion_ms <= 0:
        raise SolicitudInvalida("No se conoce la duración del video.")
    if not REGISTRO.existe(analizador.IDENTIFICADOR):
        raise NoEncontrado("El analizador no está disponible.")
    if analisis.estado_completado_con_version(
        conexion, video_id, analizador.IDENTIFICADOR, analizador.VERSION
    ):
        raise Conflicto("El audio de este video ya está analizado con esta versión.")
    return trabajos.crear(
        conexion,
        TIPO_TRABAJO,
        {"video_id": video_id, "analizador": analizador.IDENTIFICADOR},
        planificar_segmentos(datos.duracion_ms),
        al_insertar=lambda conexion_trabajo, trabajo_id: analisis.reservar_para_trabajo(
            conexion_trabajo, video_id, analizador.IDENTIFICADOR, analizador.VERSION, trabajo_id
        ),
    )
