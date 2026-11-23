"""Tarea `analisis_video`. Corre en el proceso hijo del trabajo (`app.jobs.ejecutar`).

Procesa los segmentos de fotogramas pendientes y confirma cada uno junto con sus señales y miniaturas. Un
segmento confirmado no se vuelve a procesar al reanudar. Si el trabajo falla o se cancela, el análisis pasa a
`fallido` o `cancelado` (D-057).
"""
import logging
from typing import TYPE_CHECKING, Any

from app.core.errores import Conflicto
from app.core.rutas import RaizDatos
from app.jobs import service as trabajos
from app.jobs.service import ReclamoPerdido, TrabajoCancelado
from app.modules.analisis import service as analisis
from app.modules.analisis.almacenamiento import AlmacenFotogramasVideo
from app.modules.videos import service as videos
from app.modules.vision import analizador, captura, medidas
from app.modules.vision.analizador import AnalizadorVideo, EstadoPrevioVideo
from app.modules.vision.parametros import PARAMETROS_POR_DEFECTO
from app.modules.vision.service import TIPO_SEGMENTO_CIERRE, TIPO_SEGMENTO_FOTOGRAMAS, planificar_segmentos
from app.plugins.contrato import SegmentoEntrada

if TYPE_CHECKING:
    from app.jobs.contexto import ContextoTrabajo

log = logging.getLogger("clipperai.vision")

PORCENTAJE_FOTOGRAMAS = 95


def analisis_video(payload: dict[str, Any], ctx: "ContextoTrabajo") -> None:
    video_id = int(payload["video_id"])
    analisis_id = analisis.id_analisis(ctx.conexion, video_id, analizador.IDENTIFICADOR)
    try:
        _procesar(ctx, video_id, analisis_id)
    except ReclamoPerdido:
        # Otro proceso es ahora el dueño del trabajo. No se escribe el estado desde aquí.
        raise
    except Exception as error:
        if isinstance(error, TrabajoCancelado):
            analisis.marcar_estado(ctx.conexion, analisis_id, "cancelado", ctx.trabajo_id, analisis.MENSAJE_CANCELADO)
        else:
            mensaje = str(error) if isinstance(error, captura.ErrorVideo) else f"{type(error).__name__}: {error}"
            analisis.marcar_estado(ctx.conexion, analisis_id, "fallido", ctx.trabajo_id, mensaje)
        raise


def al_terminar(conexion, trabajo_id: int, estado: str, error: str | None) -> None:
    """Gancho de `jobs` para un trabajo visual que terminó sin éxito. Misma política que el análisis de audio."""
    if estado == "cancelado":
        analisis.cerrar_por_cancelacion(conexion, trabajo_id)
    else:
        analisis.cerrar_por_fallo(conexion, trabajo_id, error or "El trabajo falló sin detalle.")


def _estado_previo(
    conexion, raiz: RaizDatos, video_id: int, analisis_id: int, inicio_ms: int
) -> EstadoPrevioVideo:
    """Lo que dejaron los segmentos anteriores: último cambio de escena, último fotograma y su firma.

    Se lee de la base porque solo cuentan los segmentos confirmados. Así un reinicio produce los mismos resultados.
    """
    ultimo_cambio = analisis.ultimo_fin_senal(conexion, analisis_id, analizador.TIPO_CAMBIO_ESCENA, inicio_ms)
    ultimo_fotograma = analisis.ultimo_tiempo_fotograma(conexion, analisis_id, inicio_ms)
    firma = None
    if ultimo_fotograma is not None:
        ruta = analisis.ruta_miniatura(conexion, raiz, video_id, analizador.IDENTIFICADOR, ultimo_fotograma)
        firma = medidas.firma(medidas.decodificar_jpeg(ruta.read_bytes()))
    return EstadoPrevioVideo(
        ultimo_cambio_ms=ultimo_cambio,
        ultimo_fotograma_ms=ultimo_fotograma,
        firma_ultimo_fotograma=firma,
    )


def _procesar(ctx: "ContextoTrabajo", video_id: int, analisis_id: int) -> None:
    conexion = ctx.conexion
    raiz = RaizDatos(ctx.ruta_db.parent)
    ruta_video = videos.ruta_para_analisis(conexion, video_id)
    datos = videos.datos_para_analisis(conexion, video_id)
    duracion_ms = datos.duracion_ms or 0
    if datos.ancho is None or datos.alto is None:
        raise captura.ErrorVideo("No se conocen las dimensiones del video.")

    # Este trabajo es el único en ejecución (un trabajo a la vez). Las miniaturas sin fila de intentos
    # anteriores se borran antes de empezar, y solo las de este video.
    try:
        analisis.barrer_fotogramas_huerfanos(conexion, raiz, video_id, excepto_trabajo=ctx.trabajo_id)
    except Conflicto:
        log.warning("Se omitió la limpieza de miniaturas porque hay otro trabajo en ejecución.")

    visual = AnalizadorVideo(dimensiones_origen=(datos.ancho, datos.alto), verificar=ctx.verificar_cancelacion)
    almacen = AlmacenFotogramasVideo(raiz, video_id)
    total = len(planificar_segmentos(duracion_ms, PARAMETROS_POR_DEFECTO.duracion_segmento_ms)) - 1

    for indice, inicio, fin in trabajos.segmentos_pendientes(conexion, ctx.trabajo_id, TIPO_SEGMENTO_FOTOGRAMAS):
        ctx.verificar_cancelacion()
        if not trabajos.marcar_segmento_procesando(
            conexion, ctx.trabajo_id, ctx.token, TIPO_SEGMENTO_FOTOGRAMAS, indice
        ):
            continue
        estado = _estado_previo(conexion, raiz, video_id, analisis_id, inicio)
        resultado = visual.analizar_segmento(SegmentoEntrada(ruta_video, inicio, fin), almacen, estado)
        trabajos.confirmar_segmento(
            conexion,
            ctx.trabajo_id,
            ctx.token,
            TIPO_SEGMENTO_FOTOGRAMAS,
            indice,
            None,
            None,
            analizador.VERSION,
            persistir=lambda conexion_trabajo, segmento=resultado: analisis.persistir_resultado(
                conexion_trabajo, raiz, analisis_id, segmento
            ),
        )
        ctx.progreso(int(PORCENTAJE_FOTOGRAMAS * (indice + 1) / max(1, total)))

    ctx.verificar_cancelacion()
    if trabajos.marcar_segmento_procesando(conexion, ctx.trabajo_id, ctx.token, TIPO_SEGMENTO_CIERRE, 0):
        trabajos.confirmar_segmento(
            conexion,
            ctx.trabajo_id,
            ctx.token,
            TIPO_SEGMENTO_CIERRE,
            0,
            None,
            None,
            analizador.VERSION,
            persistir=lambda conexion_trabajo: analisis.completar_consolidacion(
                conexion_trabajo, analisis_id, (), analizador.VERSION
            ),
        )
    ctx.progreso(100)
