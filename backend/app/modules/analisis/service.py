import logging
import sqlite3
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from app.core.errores import Conflicto, NoEncontrado, SolicitudInvalida
from app.core.rutas import RaizDatos
from app.db.conexion import transaccion_inmediata
from app.jobs import service as trabajos
from app.modules.analisis import almacenamiento, repository
from app.modules.analisis.schemas import (
    AnalisisRespuesta,
    FotogramaRespuesta,
    InicioAnalisisRespuesta,
    SenalRespuesta,
)
from app.modules.videos import service as videos
from app.plugins.contrato import TIPOS_SENAL_PERMITIDOS, ContratoInvalido, ResultadoSegmento, Senal
from app.plugins.registro import REGISTRO, AnalizadorNoRegistrado, RegistroAnalizadores

log = logging.getLogger("clipperai.analisis")

ESTADOS_VALIDOS = frozenset({"pendiente", "en_curso", "completado", "fallido", "cancelado"})
MENSAJE_CANCELADO = "Análisis cancelado."
ESTADOS_TRABAJO_ACTIVO = frozenset({"en_cola", "ejecutando"})
LIMITE_MAXIMO_CONSULTA = 2000
LIMITE_CONSULTA_POR_DEFECTO = 500
LONGITUD_ERROR_MAXIMA = 500


def _exigir_video(conexion: sqlite3.Connection, video_id: int) -> None:
    # Se valida a través del servicio de videos. Este módulo no lee la tabla videos.
    if not videos.existe(conexion, video_id):
        raise NoEncontrado("El video no existe.")


def _exigir_analisis(conexion: sqlite3.Connection, video_id: int, analizador: str) -> sqlite3.Row:
    _exigir_video(conexion, video_id)
    fila = repository.obtener_analisis(conexion, video_id, analizador)
    if fila is None:
        raise NoEncontrado("El análisis no existe.")
    return fila


def _a_respuesta(fila: sqlite3.Row) -> AnalisisRespuesta:
    return AnalisisRespuesta(
        id=fila["id"],
        video_id=fila["video_id"],
        analizador=fila["analizador"],
        version_analizador=fila["version_analizador"],
        estado=fila["estado"],
        error=fila["error"],
        creado=fila["creado"],
        actualizado=fila["actualizado"],
    )


def _validar_limite(limite: int) -> int:
    if not 1 <= limite <= LIMITE_MAXIMO_CONSULTA:
        raise SolicitudInvalida(f"El límite debe estar entre 1 y {LIMITE_MAXIMO_CONSULTA}.")
    return limite


def _respuesta_vigente(conexion: sqlite3.Connection, fila: sqlite3.Row) -> AnalisisRespuesta:
    """Respuesta del análisis. Si dice 'en curso' pero su trabajo ya no está activo, muestra 'fallido'.

    Un trabajo cancelado en cola o descartado tras varias interrupciones no vuelve a escribir el estado
    del análisis. La corrección se hace solo en la respuesta. La base se corrige al iniciar un análisis nuevo.
    """
    respuesta = _a_respuesta(fila)
    if respuesta.estado == "en_curso" and not _trabajo_activo(conexion, fila["trabajo_id"]):
        if trabajos.estado(conexion, fila["trabajo_id"]) == "cancelado":
            return respuesta.model_copy(update={"estado": "cancelado", "error": MENSAJE_CANCELADO})
        return respuesta.model_copy(
            update={"estado": "fallido", "error": "El trabajo terminó sin completar el análisis."}
        )
    return respuesta


def listar_analisis(conexion: sqlite3.Connection, video_id: int) -> list[AnalisisRespuesta]:
    _exigir_video(conexion, video_id)
    return [
        _respuesta_vigente(conexion, fila)
        for fila in repository.listar_analisis_de_video(conexion, video_id)
    ]


def obtener_analisis(
    conexion: sqlite3.Connection, video_id: int, analizador: str
) -> AnalisisRespuesta:
    return _respuesta_vigente(conexion, _exigir_analisis(conexion, video_id, analizador))


def listar_senales(
    conexion: sqlite3.Connection,
    video_id: int,
    analizador: str,
    inicio_ms: int | None = None,
    fin_ms: int | None = None,
    limite: int = LIMITE_CONSULTA_POR_DEFECTO,
    tipo: str | None = None,
) -> list[SenalRespuesta]:
    """Señales que se solapan con el intervalo pedido, opcionalmente de un solo tipo del vocabulario cerrado."""
    fila = _exigir_analisis(conexion, video_id, analizador)
    if inicio_ms is not None and fin_ms is not None and fin_ms < inicio_ms:
        raise SolicitudInvalida("fin_ms no puede ser menor que inicio_ms.")
    if tipo is not None and tipo not in TIPOS_SENAL_PERMITIDOS:
        raise SolicitudInvalida("El tipo de señal no está en el vocabulario permitido.")
    filas = repository.listar_senales(
        conexion, fila["id"], inicio_ms, fin_ms, _validar_limite(limite), tipo
    )
    return [
        SenalRespuesta(
            tipo=f["tipo"],
            inicio_ms=f["inicio_ms"],
            fin_ms=f["fin_ms"],
            valor=f["valor"],
            confianza=f["confianza"],
        )
        for f in filas
    ]


def listar_fotogramas(
    conexion: sqlite3.Connection,
    video_id: int,
    analizador: str,
    limite: int = LIMITE_CONSULTA_POR_DEFECTO,
) -> list[FotogramaRespuesta]:
    fila = _exigir_analisis(conexion, video_id, analizador)
    filas = repository.listar_fotogramas(conexion, fila["id"], _validar_limite(limite))
    return [FotogramaRespuesta(tiempo_ms=f["tiempo_ms"]) for f in filas]


def ruta_miniatura(
    conexion: sqlite3.Connection,
    raiz: RaizDatos,
    video_id: int,
    analizador: str,
    tiempo_ms: int,
) -> Path:
    """Ruta absoluta de una miniatura registrada. La ruta de la fila debe coincidir con la del almacén.

    Así, aunque la fila estuviera corrupta, nunca se sirve un archivo ajeno a `work/<video_id>/fotogramas`.
    """
    fila = _exigir_analisis(conexion, video_id, analizador)
    registro = repository.obtener_fotograma(conexion, fila["id"], tiempo_ms)
    if registro is None:
        raise NoEncontrado("La miniatura no existe.")
    esperada = almacenamiento.ruta_relativa_fotograma(video_id, tiempo_ms)
    if registro["ruta_relativa"] != esperada:
        raise NoEncontrado("La miniatura no está disponible.")
    return almacenamiento.verificar_fotograma(raiz, esperada)


def preparar_analisis(
    conexion: sqlite3.Connection,
    video_id: int,
    identificador: str,
    registro: RegistroAnalizadores = REGISTRO,
) -> AnalisisRespuesta:
    """Crea o actualiza el análisis de un video para un analizador registrado. Solo lo llama código del servidor.

    - Sin análisis previo: crea uno en estado pendiente.
    - Ya en curso: conflicto.
    - Completado con la misma versión: no cambia nada.
    - Con otra versión: borra sus señales y fotogramas (D-015). Los archivos de miniatura quedan para la limpieza.
    - Fallido o pendiente: vuelve a pendiente. Conserva resultados si la versión no cambió.
    """
    _exigir_video(conexion, video_id)
    try:
        analizador = registro.obtener(identificador)
    except AnalizadorNoRegistrado as error:
        raise NoEncontrado("El analizador no está disponible.") from error
    ahora = trabajos.ahora_iso()
    with transaccion_inmediata(conexion):
        fila = repository.obtener_analisis(conexion, video_id, identificador)
        if fila is None:
            repository.insertar_analisis(conexion, video_id, identificador, analizador.version, ahora)
        elif fila["estado"] == "en_curso":
            raise Conflicto("El análisis ya está en curso.")
        elif not (fila["estado"] == "completado" and fila["version_analizador"] == analizador.version):
            if fila["version_analizador"] != analizador.version:
                repository.borrar_resultados(conexion, fila["id"])
            repository.reiniciar_analisis(conexion, fila["id"], analizador.version, ahora)
    return _a_respuesta(repository.obtener_analisis(conexion, video_id, identificador))


def marcar_estado(
    conexion: sqlite3.Connection,
    analisis_id: int,
    estado: str,
    trabajo_id: int | None = None,
    error: str | None = None,
) -> None:
    if estado not in ESTADOS_VALIDOS:
        raise ContratoInvalido("Estado de análisis no válido.")
    texto = trabajos.mensaje_seguro(error)[:LONGITUD_ERROR_MAXIMA] if error else None
    with transaccion_inmediata(conexion):
        if repository.obtener_por_id(conexion, analisis_id) is None:
            raise NoEncontrado("El análisis no existe.")
        if estado == "cancelado":
            # Un análisis cancelado no conserva señales parciales (D-057).
            repository.borrar_resultados(conexion, analisis_id)
        repository.cambiar_estado(conexion, analisis_id, estado, trabajo_id, texto, trabajos.ahora_iso())


def persistir_resultado(
    conexion: sqlite3.Connection,
    raiz: RaizDatos,
    analisis_id: int,
    resultado: ResultadoSegmento,
) -> None:
    """Escribe las señales y los fotogramas de un segmento.

    No abre transacción propia. La abre `jobs.service.confirmar_segmento`, que también marca el
    segmento como completado. Así los resultados y el estado del segmento se confirman juntos.
    Las miniaturas deben existir en disco antes de llamar aquí.
    """
    if not isinstance(resultado, ResultadoSegmento):
        raise ContratoInvalido("El resultado del segmento no es válido.")
    fila = repository.obtener_por_id(conexion, analisis_id)
    if fila is None:
        raise NoEncontrado("El análisis no existe.")
    video_id = fila["video_id"]
    ahora = trabajos.ahora_iso()
    filas_fotogramas = []
    for fotograma in resultado.fotogramas:
        esperada = almacenamiento.ruta_relativa_fotograma(video_id, fotograma.tiempo_ms)
        if fotograma.ruta_relativa != esperada:
            raise ContratoInvalido("La ruta del fotograma no corresponde al almacén del video.")
        almacenamiento.verificar_fotograma(raiz, esperada)
        filas_fotogramas.append((analisis_id, fotograma.tiempo_ms, esperada, ahora))
    repository.insertar_senales(
        conexion,
        [
            (analisis_id, senal.tipo, senal.inicio_ms, senal.fin_ms, senal.valor, senal.confianza)
            for senal in resultado.senales
        ],
    )
    repository.insertar_fotogramas(conexion, filas_fotogramas)


def barrer_fotogramas_huerfanos(
    conexion: sqlite3.Connection, raiz: RaizDatos, video_id: int
) -> int:
    """Limpia miniaturas sin fila y temporales de un video. Devuelve cuántos archivos borró.

    Mantiene el bloqueo de escritura de SQLite durante todo el barrido. Así un trabajo nuevo no puede
    empezar a escribir miniaturas antes de que termine la comparación con la base de datos.
    """
    _exigir_video(conexion, video_id)
    with transaccion_inmediata(conexion):
        if trabajos.hay_trabajo_ejecutandose(conexion):
            raise Conflicto("Hay un trabajo en ejecución. La limpieza se hará cuando termine.")
        registradas = repository.rutas_fotogramas_de_video(conexion, video_id)
        return almacenamiento.barrer_huerfanos(raiz, video_id, registradas)


def _trabajo_activo(conexion: sqlite3.Connection, trabajo_id: int | None) -> bool:
    return trabajo_id is not None and trabajos.estado(conexion, trabajo_id) in ESTADOS_TRABAJO_ACTIVO


def id_analisis(conexion: sqlite3.Connection, video_id: int, identificador: str) -> int:
    """Identificador interno del análisis. Lo usan los procesos de análisis al confirmar resultados."""
    return int(_exigir_analisis(conexion, video_id, identificador)["id"])


def reservar_para_trabajo(
    conexion: sqlite3.Connection,
    video_id: int,
    identificador: str,
    version: str,
    trabajo_id: int,
) -> int:
    """Marca el análisis como en curso dentro de la transacción que crea su trabajo.

    Lo llama `jobs.service.crear` a través de `al_insertar`. Si el análisis ya tiene un trabajo activo,
    lanza Conflicto y no se crea ningún trabajo. Con otra versión, borra los resultados previos (D-015).
    """
    _exigir_video(conexion, video_id)
    ahora = trabajos.ahora_iso()
    fila = repository.obtener_analisis(conexion, video_id, identificador)
    if fila is None:
        analisis_id = repository.insertar_analisis(conexion, video_id, identificador, version, ahora)
    else:
        analisis_id = int(fila["id"])
        if fila["estado"] == "en_curso" and _trabajo_activo(conexion, fila["trabajo_id"]):
            raise Conflicto("El análisis ya está en curso.")
        if fila["version_analizador"] != version:
            repository.borrar_resultados(conexion, analisis_id)
        repository.reiniciar_analisis(conexion, analisis_id, version, ahora)
    repository.cambiar_estado(conexion, analisis_id, "en_curso", trabajo_id, None, ahora)
    return analisis_id


def estado_completado_con_version(
    conexion: sqlite3.Connection, video_id: int, identificador: str, version: str
) -> bool:
    fila = repository.obtener_analisis(conexion, video_id, identificador)
    return (
        fila is not None
        and fila["estado"] == "completado"
        and fila["version_analizador"] == version
    )


def serie_senales(
    conexion: sqlite3.Connection, analisis_id: int, tipo: str
) -> list[sqlite3.Row]:
    """Señales de un tipo ordenadas por tiempo. Para procesos internos, no para la API."""
    return repository.senales_por_tipo(conexion, analisis_id, tipo)


def completar_consolidacion(
    conexion: sqlite3.Connection,
    analisis_id: int,
    senales: Sequence[Senal],
    version: str,
) -> None:
    """Escribe las señales consolidadas y marca el análisis como completado.

    No abre transacción propia: la abre `jobs.service.confirmar_segmento`, que también marca el
    segmento de consolidación como completado. Así el análisis queda completo solo si todo se confirma.
    """
    fila = repository.obtener_por_id(conexion, analisis_id)
    if fila is None:
        raise NoEncontrado("El análisis no existe.")
    if fila["version_analizador"] != version:
        raise ContratoInvalido("La versión del analizador cambió durante el análisis.")
    repository.insertar_senales(
        conexion,
        [
            (analisis_id, senal.tipo, senal.inicio_ms, senal.fin_ms, senal.valor, senal.confianza)
            for senal in senales
        ],
    )
    repository.cambiar_estado(
        conexion, analisis_id, "completado", fila["trabajo_id"], None, trabajos.ahora_iso()
    )


Lanzador = Callable[[sqlite3.Connection, int], int]


def _exigir_disponible(conexion: sqlite3.Connection, video_id: int) -> None:
    try:
        videos.ruta_para_analisis(conexion, video_id)
    except NoEncontrado as error:
        raise Conflicto("El archivo original no está disponible.") from error


def _inicio_en_curso(conexion: sqlite3.Connection, identificador: str, trabajo_id: int | None) -> InicioAnalisisRespuesta:
    return InicioAnalisisRespuesta(
        analizador=identificador,
        accion="en_curso",
        trabajo_id=trabajo_id,
        estado=trabajos.estado(conexion, trabajo_id) if trabajo_id is not None else None,
        detalle=None,
    )


def _iniciar_uno(
    conexion: sqlite3.Connection, video_id: int, identificador: str, lanzador: Lanzador
) -> InicioAnalisisRespuesta:
    version = REGISTRO.obtener(identificador).version
    fila = repository.obtener_analisis(conexion, video_id, identificador)
    if fila is not None:
        if fila["estado"] == "en_curso" and _trabajo_activo(conexion, fila["trabajo_id"]):
            return _inicio_en_curso(conexion, identificador, fila["trabajo_id"])
        if fila["estado"] == "completado" and fila["version_analizador"] == version:
            return InicioAnalisisRespuesta(
                analizador=identificador, accion="sin_cambios", trabajo_id=None, estado="completado", detalle=None
            )
    try:
        trabajo_id = lanzador(conexion, video_id)
    except Conflicto:
        # Otra petición inició el análisis entre la consulta y la escritura. Se devuelve ese trabajo.
        fila = repository.obtener_analisis(conexion, video_id, identificador)
        return _inicio_en_curso(conexion, identificador, fila["trabajo_id"] if fila is not None else None)
    except SolicitudInvalida as error:
        return InicioAnalisisRespuesta(
            analizador=identificador, accion="rechazado", trabajo_id=None, estado=None, detalle=error.mensaje
        )
    return InicioAnalisisRespuesta(
        analizador=identificador,
        accion="iniciado",
        trabajo_id=trabajo_id,
        estado=trabajos.estado(conexion, trabajo_id),
        detalle=None,
    )


def iniciar(
    conexion: sqlite3.Connection, video_id: int, lanzadores: Mapping[str, Lanzador]
) -> list[InicioAnalisisRespuesta]:
    """Inicia cada analizador registrado que tenga lanzador. Un análisis activo o completo no se repite.

    Un análisis fallido o cancelado se reintenta. Cada analizador tiene su propia transacción: un rechazo
    de uno no impide iniciar los demás.
    """
    _exigir_video(conexion, video_id)
    _exigir_disponible(conexion, video_id)
    return [
        _iniciar_uno(conexion, video_id, identificador, lanzadores[identificador])
        for identificador in sorted(lanzadores)
        if REGISTRO.existe(identificador)
    ]


def cerrar_por_fallo(conexion: sqlite3.Connection, trabajo_id: int, error: str) -> None:
    """Pasa a fallido los análisis en curso de un trabajo que falló. Conserva sus resultados (D-044).

    Lo llama el gancho de cierre de `jobs` dentro de su transacción. No abre transacción propia.
    """
    for analisis_id in repository.ids_en_curso_de_trabajo(conexion, trabajo_id):
        repository.cambiar_estado(
            conexion, analisis_id, "fallido", trabajo_id, error[:LONGITUD_ERROR_MAXIMA], trabajos.ahora_iso()
        )


def cerrar_por_cancelacion(conexion: sqlite3.Connection, trabajo_id: int) -> None:
    """Pasa a cancelado los análisis en curso de un trabajo cancelado, borrando sus resultados parciales.

    Lo llama el gancho de cancelación de `jobs`, según el tipo de trabajo. No abre transacción propia:
    corre dentro de la transacción de quien cancela o del supervisor. Solo cambia análisis en curso con ese
    trabajo, así que llamarlo dos veces no tiene efecto adicional.
    """
    for analisis_id in repository.ids_en_curso_de_trabajo(conexion, trabajo_id):
        repository.borrar_resultados(conexion, analisis_id)
        repository.cambiar_estado(
            conexion, analisis_id, "cancelado", trabajo_id, MENSAJE_CANCELADO, trabajos.ahora_iso()
        )


def preparar_eliminacion(conexion: sqlite3.Connection, video_id: int) -> None:
    """Paso de eliminación de un video. Lo llama `videos.service.eliminar` dentro de su transacción.

    No abre transacción propia. Lanza Conflicto si un análisis del video tiene un trabajo activo.
    Borra los análisis del video; sus señales y fotogramas se borran en cascada.
    """
    for fila in repository.trabajos_en_curso_de_video(conexion, video_id):
        if _trabajo_activo(conexion, fila["trabajo_id"]):
            raise Conflicto("Hay un análisis en curso para este video. Espere a que termine o cancélelo.")
    repository.borrar_analisis_de_video(conexion, video_id)


def borrar_archivos_derivados(raiz: RaizDatos, video_id: int) -> int:
    """Borra las miniaturas del video una vez confirmada la base. Devuelve cuántas borró.

    Un fallo no se propaga: el registro del video ya no existe, y los archivos que no se borren
    quedan huérfanos hasta la limpieza de arranque (`limpiar_derivados_huerfanos`).
    """
    try:
        borrados, fallidos = almacenamiento.borrar_fotogramas_de_video(raiz, video_id)
    except OSError:
        log.warning("No se pudieron revisar las miniaturas del video %s. Quedan para la limpieza de arranque.", video_id)
        return 0
    if fallidos:
        log.warning(
            "No se pudieron borrar %s miniaturas del video %s. Quedan para la limpieza de arranque.",
            fallidos,
            video_id,
        )
    return borrados


def limpiar_derivados_huerfanos(conexion: sqlite3.Connection, raiz: RaizDatos) -> int:
    """Retira miniaturas de videos que ya no están en la base. Se llama al arrancar el backend.

    Solo toca directorios `work/<id>` cuyo id no existe en `videos`. Nunca toca el original de un video.
    Devuelve cuántos archivos borró.
    """
    existentes = videos.ids_existentes(conexion)
    try:
        borrados, fallidos = almacenamiento.barrer_videos_eliminados(raiz, existentes)
    except OSError:
        log.warning("No se pudo completar la limpieza de miniaturas huérfanas.")
        return 0
    if fallidos:
        log.warning("%s miniaturas huérfanas no se pudieron borrar. Se reintentará al arrancar.", fallidos)
    return borrados

