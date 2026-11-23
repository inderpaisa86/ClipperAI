"""Registro de analizadores y tipos de trabajo. Lo llaman la API y el proceso hijo de cada trabajo.

Es el único lugar donde `jobs` recibe tareas de los módulos de análisis. Así `jobs` no importa a esos
módulos y no hay importaciones circulares. Registrar dos veces el mismo elemento no tiene efecto.
"""

from collections.abc import Callable

from app.jobs import tareas
from app.modules.audio import analizador as analizador_audio
from app.modules.audio import service as servicio_audio
from app.modules.audio import tarea as tarea_audio
from app.plugins.registro import REGISTRO


def registrar() -> None:
    analizador_audio.registrar(REGISTRO)
    tareas.registrar(
        servicio_audio.TIPO_TRABAJO,
        tarea_audio.analisis_audio,
        al_terminar=tarea_audio.al_terminar,
    )


def lanzadores() -> dict[str, Callable]:
    """Función que inicia el análisis de cada analizador disponible en la API. Firma: (conexión, video_id) -> trabajo_id."""
    return {analizador_audio.IDENTIFICADOR: servicio_audio.iniciar_analisis}
