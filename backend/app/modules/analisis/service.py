import sqlite3
from pathlib import Path

from app.core.errores import Conflicto, NoEncontrado, SolicitudInvalida
from app.core.rutas import RaizDatos
from app.db.conexion import transaccion_inmediata
from app.jobs import service as trabajos
from app.modules.analisis import almacenamiento, repository
from app.modules.analisis.schemas import AnalisisRespuesta, FotogramaRespuesta, SenalRespuesta
from app.modules.videos import service as videos
from app.plugins.contrato import ContratoInvalido, ResultadoSegmento
from app.plugins.registro import REGISTRO, AnalizadorNoRegistrado, RegistroAnalizadores

ESTADOS_VALIDOS = frozenset({"pendiente", "en_curso", "completado", "fallido"})
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


def listar_analisis(conexion: sqlite3.Connection, video_id: int) -> list[AnalisisRespuesta]:
    _exigir_video(conexion, video_id)
    return [_a_respuesta(fila) for fila in repository.listar_analisis_de_video(conexion, video_id)]


def obtener_analisis(
    conexion: sqlite3.Connection, video_id: int, analizador: str
) -> AnalisisRespuesta:
    return _a_respuesta(_exigir_analisis(conexion, video_id, analizador))


def listar_senales(
    conexion: sqlite3.Connection,
    video_id: int,
    analizador: str,
    inicio_ms: int | None = None,
    fin_ms: int | None = None,
    limite: int = LIMITE_CONSULTA_POR_DEFECTO,
) -> list[SenalRespuesta]:
    """Señales que se solapan con el intervalo pedido. Sin intervalo, devuelve las primeras del análisis."""
    fila = _exigir_analisis(conexion, video_id, analizador)
    if inicio_ms is not None and fin_ms is not None and fin_ms < inicio_ms:
        raise SolicitudInvalida("fin_ms no puede ser menor que inicio_ms.")
    filas = repository.listar_senales(
        conexion, fila["id"], inicio_ms, fin_ms, _validar_limite(limite)
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
