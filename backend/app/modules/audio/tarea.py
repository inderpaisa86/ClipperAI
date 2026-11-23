"""Tarea `analisis_audio`. Corre en el proceso hijo del trabajo (`app.jobs.ejecutar`).

Procesa los segmentos de energía pendientes y confirma cada uno junto con sus señales. Al final calcula
los silencios y los cambios de intensidad sobre la serie completa y completa el análisis. Si el trabajo
falla o se cancela, el análisis queda en estado `fallido` con un mensaje corto.
"""

import math
from typing import TYPE_CHECKING, Any

from app.core.rutas import RaizDatos
from app.jobs import service as trabajos
from app.jobs.service import ReclamoPerdido, TrabajoCancelado
from app.modules.analisis import service as analisis
from app.modules.audio import analizador, energia
from app.modules.audio.senales import PuntoEnergia, TIPO_ENERGIA, consolidar
from app.modules.audio.service import (
    DURACION_SEGMENTO_MS,
    TIPO_SEGMENTO_CONSOLIDACION,
    TIPO_SEGMENTO_ENERGIA,
)
from app.modules.videos import service as videos
from app.plugins.contrato import SegmentoEntrada

if TYPE_CHECKING:
    from app.jobs.contexto import ContextoTrabajo

PORCENTAJE_ENERGIA = 90


def analisis_audio(payload: dict[str, Any], ctx: "ContextoTrabajo") -> None:
    video_id = int(payload["video_id"])
    analisis_id = analisis.id_analisis(ctx.conexion, video_id, analizador.IDENTIFICADOR)
    try:
        _procesar(ctx, video_id, analisis_id)
    except ReclamoPerdido:
        # Otro proceso es ahora el dueño del trabajo. No se escribe el estado desde aquí.
        raise
    except Exception as error:
        if isinstance(error, TrabajoCancelado):
            # Cancelación observada por el proceso: el análisis pasa a cancelado sin resultados parciales (D-057).
            analisis.marcar_estado(ctx.conexion, analisis_id, "cancelado", ctx.trabajo_id, analisis.MENSAJE_CANCELADO)
        else:
            mensaje = str(error) if isinstance(error, energia.ErrorAudio) else f"{type(error).__name__}: {error}"
            analisis.marcar_estado(ctx.conexion, analisis_id, "fallido", ctx.trabajo_id, mensaje)
        raise


def al_terminar(conexion, trabajo_id: int, estado: str, error: str | None) -> None:
    """Gancho de `jobs`: cierra el análisis de un trabajo de audio que terminó sin éxito.

    Lo llama `jobs` en la misma transacción que marca el trabajo, también cuando el supervisor termina el
    proceso. Así el análisis no depende de que el proceso hijo llegue a cerrarlo.
    """
    if estado == "cancelado":
        analisis.cerrar_por_cancelacion(conexion, trabajo_id)
    else:
        analisis.cerrar_por_fallo(conexion, trabajo_id, error or "El trabajo falló sin detalle.")


def _procesar(ctx: "ContextoTrabajo", video_id: int, analisis_id: int) -> None:
    conexion = ctx.conexion
    raiz = RaizDatos(ctx.ruta_db.parent)
    ruta_video = videos.ruta_para_analisis(conexion, video_id)
    duracion_ms = videos.datos_para_analisis(conexion, video_id).duracion_ms or 0
    total_segmentos = max(1, math.ceil(duracion_ms / DURACION_SEGMENTO_MS))
    analizador_audio = analizador.AnalizadorAudio(verificar=ctx.verificar_cancelacion)

    for indice, inicio, fin in trabajos.segmentos_pendientes(conexion, ctx.trabajo_id, TIPO_SEGMENTO_ENERGIA):
        ctx.verificar_cancelacion()
        if not trabajos.marcar_segmento_procesando(
            conexion, ctx.trabajo_id, ctx.token, TIPO_SEGMENTO_ENERGIA, indice
        ):
            continue
        resultado = analizador_audio.analizar_segmento(SegmentoEntrada(ruta_video, inicio, fin))
        esperadas = (fin - inicio) // energia.VENTANA_MS
        if len(resultado.senales) < esperadas and fin < duracion_ms:
            raise energia.ErrorAudio("El audio del video termina antes de lo que indica su duración.")
        trabajos.confirmar_segmento(
            conexion,
            ctx.trabajo_id,
            ctx.token,
            TIPO_SEGMENTO_ENERGIA,
            indice,
            None,
            None,
            analizador.VERSION,
            persistir=lambda conexion_trabajo, segmento=resultado: analisis.persistir_resultado(
                conexion_trabajo, raiz, analisis_id, segmento
            ),
        )
        ctx.progreso(int(PORCENTAJE_ENERGIA * (indice + 1) / total_segmentos))

    ctx.verificar_cancelacion()
    if not trabajos.marcar_segmento_procesando(
        conexion, ctx.trabajo_id, ctx.token, TIPO_SEGMENTO_CONSOLIDACION, 0
    ):
        return
    filas = analisis.serie_senales(conexion, analisis_id, TIPO_ENERGIA)
    puntos = [
        PuntoEnergia(
            inicio_ms=int(fila["inicio_ms"]),
            fin_ms=int(fila["fin_ms"]),
            nivel_db=energia.db_desde_valor(float(fila["valor"])),
        )
        for fila in filas
    ]
    senales = consolidar(puntos)
    trabajos.confirmar_segmento(
        conexion,
        ctx.trabajo_id,
        ctx.token,
        TIPO_SEGMENTO_CONSOLIDACION,
        0,
        None,
        None,
        analizador.VERSION,
        persistir=lambda conexion_trabajo: analisis.completar_consolidacion(
            conexion_trabajo, analisis_id, senales, analizador.VERSION
        ),
    )
    ctx.progreso(100)
