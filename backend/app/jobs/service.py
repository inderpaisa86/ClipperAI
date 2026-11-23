import json
import re
import sqlite3
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any

from app.core.errores import NoEncontrado, SolicitudInvalida
from app.jobs import repository, tareas

PAYLOAD_MAXIMO_BYTES = 16 * 1024
LONGITUD_ERROR = 500
PROGRESO_MINIMO = 0
PROGRESO_MAXIMO = 100


class ReclamoPerdido(Exception):
    """El proceso que llama ya no es el dueño vigente del trabajo."""


class TrabajoCancelado(Exception):
    """El trabajo tiene una cancelación solicitada y no puede confirmar resultados."""


def ahora_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


@contextmanager
def _transaccion(conexion: sqlite3.Connection) -> Iterator[None]:
    """Transacción con escritura reservada desde el inicio. Dos procesos no escriben a la vez."""
    conexion.execute("BEGIN IMMEDIATE")
    try:
        yield
    except BaseException:
        if conexion.in_transaction:
            conexion.execute("ROLLBACK")
        raise
    conexion.execute("COMMIT")


def mensaje_seguro(texto: str) -> str:
    """Quita rutas del sistema de un mensaje antes de guardarlo o mostrarlo."""
    limpio = re.sub(r"\\\\[^\s'\"<>|]+", "<ruta>", texto)
    limpio = re.sub(r"[A-Za-z]:\\[^\s'\"<>|]*", "<ruta>", limpio)
    limpio = re.sub(r"(?<![\w:])/(?:[^\s/'\"<>|]+/)+[^\s'\"<>|]*", "<ruta>", limpio)
    limpio = "".join(caracter if caracter.isprintable() or caracter == " " else " " for caracter in limpio)
    return limpio.strip()[:LONGITUD_ERROR] or "Error sin detalle."


def latido_vencido(latido: str | None, umbral_segundos: float) -> bool:
    if latido is None:
        return True
    marca = datetime.fromisoformat(latido.replace("Z", "+00:00"))
    return (datetime.now(timezone.utc) - marca).total_seconds() > umbral_segundos


def _respuesta(fila: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": fila["id"],
        "tipo": fila["tipo"],
        "estado": fila["estado"],
        "progreso": fila["progreso"],
        "cancelacion_solicitada": bool(fila["cancelacion_solicitada"]),
        "intentos": fila["intentos"],
        "error": fila["error"],
        "creado": fila["creado"],
        "actualizado": fila["actualizado"],
    }


def _fila_o_error(conexion: sqlite3.Connection, trabajo_id: int) -> sqlite3.Row:
    fila = repository.obtener(conexion, trabajo_id)
    if fila is None:
        raise NoEncontrado("El trabajo no existe.")
    return fila


def crear(
    conexion: sqlite3.Connection,
    tipo: str,
    payload: dict[str, Any],
    segmentos: Iterable[tuple[str, int, int, int]] = (),
    al_insertar: Callable[[sqlite3.Connection, int], None] | None = None,
) -> int:
    """Crea un trabajo en cola. Solo el código del servidor llama a esta función, nunca un cliente HTTP.
    `al_insertar` recibe el id nuevo dentro de la misma transacción. Si lanza una excepción, no se crea
    el trabajo. Así un módulo puede registrar su propio estado junto con el trabajo.
    """
    if not tareas.existe(tipo):
        raise SolicitudInvalida("Tipo de trabajo no admitido.")
    datos = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if len(datos.encode("utf-8")) > PAYLOAD_MAXIMO_BYTES:
        raise SolicitudInvalida("El payload del trabajo es demasiado grande.")
    ahora = ahora_iso()
    with _transaccion(conexion):
        trabajo_id = repository.insertar_trabajo(conexion, tipo, datos, ahora)
        repository.insertar_segmentos(conexion, trabajo_id, segmentos, ahora)
        if al_insertar is not None:
            al_insertar(conexion, trabajo_id)
    return trabajo_id
def estado(conexion: sqlite3.Connection, trabajo_id: int) -> str | None:
    """Estado actual del trabajo, o None si no existe. Otros módulos lo usan para saber si un trabajo sigue vivo."""
    fila = repository.obtener(conexion, trabajo_id)
    return None if fila is None else str(fila["estado"])
def segmentos_pendientes(
    conexion: sqlite3.Connection, trabajo_id: int, tipo: str
) -> list[tuple[int, int, int]]:
    """Segmentos de un tipo que aún no se completaron, como (indice, inicio_ms, fin_ms), en orden."""
    return [
        (int(fila["indice"]), int(fila["inicio_ms"]), int(fila["fin_ms"]))
        for fila in repository.segmentos_pendientes(conexion, trabajo_id, tipo)
    ]


def consultar(conexion: sqlite3.Connection, trabajo_id: int) -> dict[str, Any]:
    return _respuesta(_fila_o_error(conexion, trabajo_id))


def cancelar(conexion: sqlite3.Connection, trabajo_id: int) -> dict[str, Any]:
    """Cancelación idempotente. En cola pasa a cancelado. En ejecución marca la solicitud y el proceso se detiene."""
    ahora = ahora_iso()
    with _transaccion(conexion):
        fila = _fila_o_error(conexion, trabajo_id)
        if fila["estado"] == "en_cola":
            repository.cancelar_en_cola(conexion, trabajo_id, ahora)
            _al_terminar(conexion, trabajo_id, fila["tipo"], "cancelado", None)
        elif fila["estado"] == "ejecutando":
            repository.marcar_cancelacion_en_ejecucion(conexion, trabajo_id, ahora)
    return consultar(conexion, trabajo_id)


def reclamar_siguiente(conexion: sqlite3.Connection, token: str) -> int | None:
    """Toma el trabajo más antiguo en cola. Devuelve None si no hay ninguno o si otro ya se ejecuta."""
    with _transaccion(conexion):
        if repository.hay_ejecucion(conexion):
            return None
        trabajo_id = repository.primer_en_cola(conexion)
        if trabajo_id is None:
            return None
        if repository.reclamar(conexion, trabajo_id, token, ahora_iso()) != 1:
            return None
    return trabajo_id


def registrar_proceso(
    conexion: sqlite3.Connection, trabajo_id: int, token: str, pid: int, identidad: str
) -> bool:
    with _transaccion(conexion):
        return repository.registrar_proceso(conexion, trabajo_id, token, pid, identidad, ahora_iso()) == 1


def leer_control(conexion: sqlite3.Connection, trabajo_id: int, token: str) -> dict[str, Any] | None:
    """Estado de control para el supervisor. None si el token ya no es el vigente."""
    fila = repository.obtener_ejecucion(conexion, trabajo_id, token)
    if fila is None:
        return None
    return {"cancelacion_solicitada": bool(fila["cancelacion_solicitada"])}


def latido(
    conexion: sqlite3.Connection,
    trabajo_id: int,
    token: str,
    progreso: int | None = None,
) -> bool:
    """Renueva el latido y devuelve si hay cancelación solicitada. Con un token ajeno lanza ReclamoPerdido."""
    if progreso is not None:
        progreso = min(max(int(progreso), PROGRESO_MINIMO), PROGRESO_MAXIMO)
    with _transaccion(conexion):
        fila = repository.obtener_ejecucion(conexion, trabajo_id, token)
        if fila is None:
            raise ReclamoPerdido()
        repository.actualizar_latido(conexion, trabajo_id, token, progreso, ahora_iso())
        return bool(fila["cancelacion_solicitada"])


def completar(conexion: sqlite3.Connection, trabajo_id: int, token: str) -> bool:
    """Marca completado. Devuelve False si hay cancelación pendiente o si el token ya no es el vigente."""
    with _transaccion(conexion):
        return repository.terminar(
            conexion, trabajo_id, token, "completado", None, True, ahora_iso()
        ) == 1


def fallar(conexion: sqlite3.Connection, trabajo_id: int, token: str, mensaje: str) -> bool:
    ahora = ahora_iso()
    with _transaccion(conexion):
        texto = mensaje_seguro(mensaje)
        if repository.terminar(conexion, trabajo_id, token, "fallido", texto, False, ahora) != 1:
            return False
        repository.cambiar_segmentos_procesando(conexion, trabajo_id, "fallido", ahora)
        _al_terminar(conexion, trabajo_id, repository.obtener(conexion, trabajo_id)["tipo"], "fallido", texto)
    return True


MOTIVOS_TERMINACION = frozenset({"salida", "parada", "cancelacion_forzada"})


def _al_terminar(
    conexion: sqlite3.Connection, trabajo_id: int, tipo: str, estado: str, error: str | None
) -> None:
    """Llama al gancho de cierre sin éxito del tipo, si lo tiene. Corre en la misma transacción que el cierre."""
    gancho = tareas.gancho_terminar(tipo)
    if gancho is not None:
        gancho(conexion, trabajo_id, estado, error)


def cancelar_ejecucion(conexion: sqlite3.Connection, trabajo_id: int, token: str) -> bool:
    """Cierre pedido por el propio proceso del trabajo tras detectar la cancelación."""
    ahora = ahora_iso()
    with _transaccion(conexion):
        if repository.terminar(conexion, trabajo_id, token, "cancelado", None, False, ahora) != 1:
            return False
        repository.cambiar_segmentos_procesando(conexion, trabajo_id, "fallido", ahora)
        _al_terminar(conexion, trabajo_id, repository.obtener(conexion, trabajo_id)["tipo"], "cancelado", None)
    return True


def cerrar_tras_proceso(
    conexion: sqlite3.Connection,
    trabajo_id: int,
    token: str,
    codigo: int | None,
    motivo: str,
) -> str:
    """Decide el estado final tras salir del proceso hijo, si el hijo no lo dejó cerrado.

    `motivo` dice por qué terminó el proceso, y es lo que separa una cancelación de un fallo:
    - `cancelacion_forzada`: el supervisor lo terminó tras la gracia de cancelación. Es una cancelación.
    - `parada`: parada ordenada del worker. Si hay cancelación pedida, es cancelación. Si no, se reencola.
    - `salida`: el proceso terminó solo. Sin resultado confirmado es un fallo, aunque haya cancelación pedida.
      Así un error real nunca se registra como cancelación.
    """
    if motivo not in MOTIVOS_TERMINACION:
        raise ValueError("Motivo de terminación no válido.")
    ahora = ahora_iso()
    with _transaccion(conexion):
        fila = repository.obtener_ejecucion(conexion, trabajo_id, token)
        if fila is None:
            return "ya_cerrado"
        cancelacion_pedida = bool(fila["cancelacion_solicitada"])
        if cancelacion_pedida and motivo in ("cancelacion_forzada", "parada"):
            repository.terminar(conexion, trabajo_id, token, "cancelado", None, False, ahora)
            repository.cambiar_segmentos_procesando(conexion, trabajo_id, "fallido", ahora)
            _al_terminar(conexion, trabajo_id, fila["tipo"], "cancelado", None)
            return "cancelado"
        if motivo == "parada":
            # Parada ordenada: no es un fallo ni un intento real, así que no aplica el límite de intentos.
            if repository.reencolar_por_parada(conexion, trabajo_id, token, ahora) != 1:
                return "ya_cerrado"
            repository.cambiar_segmentos_procesando(conexion, trabajo_id, "pendiente", ahora)
            return "reencolado"
        mensaje = f"El proceso terminó sin confirmar el resultado (código {codigo})."
        repository.terminar(conexion, trabajo_id, token, "fallido", mensaje, False, ahora)
        repository.cambiar_segmentos_procesando(conexion, trabajo_id, "fallido", ahora)
        _al_terminar(conexion, trabajo_id, fila["tipo"], "fallido", mensaje)
        return "fallido"


def reencolar_interrumpido(
    conexion: sqlite3.Connection,
    trabajo_id: int,
    token: str,
    max_intentos: int,
) -> str:
    """Devuelve a cola un trabajo cuyo proceso desapareció. Respeta la cancelación y el límite de intentos."""
    ahora = ahora_iso()
    with _transaccion(conexion):
        fila = repository.obtener_ejecucion(conexion, trabajo_id, token)
        if fila is None:
            return "sin_cambio"
        return _reencolar_o_fallar(conexion, trabajo_id, token, fila, max_intentos, ahora)


def _reencolar_o_fallar(
    conexion: sqlite3.Connection,
    trabajo_id: int,
    token: str,
    fila: sqlite3.Row,
    max_intentos: int,
    ahora: str,
) -> str:
    if fila["cancelacion_solicitada"]:
        repository.terminar(conexion, trabajo_id, token, "cancelado", None, False, ahora)
        repository.cambiar_segmentos_procesando(conexion, trabajo_id, "fallido", ahora)
        _al_terminar(conexion, trabajo_id, fila["tipo"], "cancelado", None)
        return "cancelado"
    if fila["intentos"] >= max_intentos:
        mensaje = f"El trabajo se interrumpió {fila['intentos']} veces y no se reintentará."
        repository.terminar(conexion, trabajo_id, token, "fallido", mensaje, False, ahora)
        repository.cambiar_segmentos_procesando(conexion, trabajo_id, "fallido", ahora)
        _al_terminar(conexion, trabajo_id, fila["tipo"], "fallido", mensaje)
        return "fallido"
    repository.reencolar(conexion, trabajo_id, token, ahora)
    repository.cambiar_segmentos_procesando(conexion, trabajo_id, "pendiente", ahora)
    return "reencolado"

def listar_ejecucion(conexion: sqlite3.Connection) -> list[sqlite3.Row]:
    return repository.listar_ejecucion(conexion)


def marcar_segmento_procesando(
    conexion: sqlite3.Connection, trabajo_id: int, token: str, tipo: str, indice: int
) -> bool:
    with _transaccion(conexion):
        if repository.obtener_ejecucion(conexion, trabajo_id, token) is None:
            raise ReclamoPerdido()
        return repository.marcar_segmento_procesando(conexion, trabajo_id, tipo, indice, ahora_iso()) == 1


def confirmar_segmento(
    conexion: sqlite3.Connection,
    trabajo_id: int,
    token: str,
    tipo: str,
    indice: int,
    salida_ruta: str | None,
    salida_tamano: int | None,
    version_analizador: str | None,
    persistir: Callable[[sqlite3.Connection], None] | None = None,
) -> bool:
    """Confirma un segmento. Lanza ReclamoPerdido o TrabajoCancelado si el resultado ya no debe escribirse.

    `persistir` escribe los resultados del segmento (por ejemplo, las señales de un módulo de análisis)
    dentro de la misma transacción que marca el segmento como completado. Si `persistir` lanza una
    excepción, se deshacen ambas escrituras. Este módulo no conoce las tablas que escribe `persistir`.
    """
    with _transaccion(conexion):
        fila = repository.obtener_ejecucion(conexion, trabajo_id, token)
        if fila is None:
            raise ReclamoPerdido()
        if fila["cancelacion_solicitada"]:
            raise TrabajoCancelado()
        confirmado = repository.confirmar_segmento(
            conexion, trabajo_id, tipo, indice, salida_ruta, salida_tamano, version_analizador, ahora_iso()
        ) == 1
        if confirmado and persistir is not None:
            persistir(conexion)
        return confirmado


def hay_trabajo_ejecutandose(conexion: sqlite3.Connection) -> bool:
    """True si un trabajo pesado está en curso. Otros módulos lo consultan antes de tareas de mantenimiento."""
    return repository.hay_ejecucion(conexion)
