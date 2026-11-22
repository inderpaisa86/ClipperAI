"""Proceso hijo de un trabajo: `python -m app.jobs.ejecutar <id> <token> <db> <directorio> <intervalo>`.

Códigos de salida: 0 terminado (completado o cancelado), 1 fallo de la tarea,
2 no se pudo registrar el proceso, 3 el reclamo se perdió durante la ejecución.
"""

import json
import logging
import os
import sqlite3
import sys
from pathlib import Path

from app.core import plataforma
from app.db.conexion import conectar
from app.jobs import service, tareas
from app.jobs.contexto import ContextoTrabajo
from app.jobs.service import ReclamoPerdido, TrabajoCancelado

log = logging.getLogger("clipperai.jobs")

SALIDA_OK = 0
SALIDA_FALLO = 1
SALIDA_NO_REGISTRADO = 2
SALIDA_RECLAMO_PERDIDO = 3


def ejecutar(
    trabajo_id: int,
    token: str,
    ruta_db: Path,
    directorio: Path,
    intervalo_latido: float,
) -> int:
    conexion = conectar(ruta_db)
    contexto: ContextoTrabajo | None = None
    try:
        identidad = plataforma.identidad_proceso(os.getpid())
        if identidad is None or not service.registrar_proceso(
            conexion, trabajo_id, token, os.getpid(), identidad
        ):
            return SALIDA_NO_REGISTRADO

        fila = service.consultar(conexion, trabajo_id)
        tipo = fila["tipo"]
        payload = json.loads(_payload_crudo(conexion, trabajo_id))
        tarea = tareas.obtener(tipo)
        if tarea is None:
            service.fallar(conexion, trabajo_id, token, f"Tipo de trabajo desconocido: {tipo}.")
            return SALIDA_FALLO

        directorio.mkdir(parents=True, exist_ok=True)
        contexto = ContextoTrabajo(
            ruta_db, conexion, trabajo_id, token, payload, directorio, intervalo_latido
        )
        contexto.iniciar_latidos()
        try:
            tarea(payload, contexto)
            contexto.verificar_cancelacion()
            if service.completar(conexion, trabajo_id, token):
                return SALIDA_OK
            service.cancelar_ejecucion(conexion, trabajo_id, token)
            return SALIDA_OK
        except TrabajoCancelado:
            service.cancelar_ejecucion(conexion, trabajo_id, token)
            return SALIDA_OK
        except ReclamoPerdido:
            return SALIDA_RECLAMO_PERDIDO
        except Exception as error:  # noqa: BLE001 - cualquier fallo de la tarea debe quedar registrado
            # Solo el tipo de excepción y su mensaje, sin trazas ni rutas. mensaje_seguro quita las rutas.
            service.fallar(conexion, trabajo_id, token, f"{type(error).__name__}: {error}")
            return SALIDA_FALLO
    except ReclamoPerdido:
        return SALIDA_RECLAMO_PERDIDO
    finally:
        if contexto is not None:
            contexto.cerrar()
        conexion.close()


def _payload_crudo(conexion: sqlite3.Connection, trabajo_id: int) -> str:
    fila = conexion.execute("SELECT payload_json FROM trabajos WHERE id = ?", (trabajo_id,)).fetchone()
    return fila["payload_json"] if fila is not None else "{}"


def _principal(argumentos: list[str]) -> int:
    if len(argumentos) != 5:
        return SALIDA_FALLO
    return ejecutar(
        int(argumentos[0]),
        argumentos[1],
        Path(argumentos[2]),
        Path(argumentos[3]),
        float(argumentos[4]),
    )


if __name__ == "__main__":
    sys.exit(_principal(sys.argv[1:]))
