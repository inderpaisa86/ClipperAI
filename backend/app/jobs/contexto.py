import logging
import os
import sqlite3
import threading
from pathlib import Path

from app.core import plataforma
from app.db.conexion import conectar
from app.jobs import service
from app.jobs.service import ReclamoPerdido, TrabajoCancelado

log = logging.getLogger("clipperai.jobs")

CODIGO_SALIDA_RECLAMO_PERDIDO = 3


class ContextoTrabajo:
    """Lo que una tarea ve del trabajo: payload, directorio propio, progreso y cancelación.

    Un hilo propio renueva el latido, comprueba la cancelación y detecta si el proceso perdió su reclamo.
    Ese hilo usa su propia conexión. La conexión principal solo la usa el hilo de la tarea.
    """

    def __init__(
        self,
        ruta_db: Path,
        conexion: sqlite3.Connection,
        trabajo_id: int,
        token: str,
        payload: dict,
        directorio: Path,
        intervalo_latido: float,
    ) -> None:
        self._ruta_db = ruta_db
        self._conexion = conexion
        self._trabajo_id = trabajo_id
        self._token = token
        self.payload = payload
        self.directorio = directorio
        self._intervalo = intervalo_latido
        self._cancelado = threading.Event()
        self._detener = threading.Event()
        self._hilo: threading.Thread | None = None
        self._padre = os.getppid()

    def iniciar_latidos(self) -> None:
        self._hilo = threading.Thread(target=self._bucle_latidos, name="latidos-trabajo", daemon=True)
        self._hilo.start()

    def cerrar(self) -> None:
        self._detener.set()
        if self._hilo is not None:
            self._hilo.join(timeout=5)

    def cancelado(self) -> bool:
        return self._cancelado.is_set()

    def verificar_cancelacion(self) -> None:
        if self._cancelado.is_set():
            raise TrabajoCancelado()

    def progreso(self, valor: int) -> None:
        """Actualiza el progreso y renueva el latido. Lanza ReclamoPerdido si el token ya no es válido."""
        if service.latido(self._conexion, self._trabajo_id, self._token, valor):
            self._cancelado.set()

    def _bucle_latidos(self) -> None:
        conexion = conectar(self._ruta_db)
        try:
            while not self._detener.wait(self._intervalo):
                if os.getppid() != self._padre:
                    self._abortar("El proceso padre terminó.")
                try:
                    if service.latido(conexion, self._trabajo_id, self._token):
                        self._cancelado.set()
                except ReclamoPerdido:
                    self._abortar("El trabajo fue reasignado.")
                except sqlite3.Error:
                    # Un bloqueo transitorio de SQLite no es motivo para abandonar el trabajo.
                    log.warning("Latido omitido por un error transitorio de la base de datos.")
        finally:
            conexion.close()

    def _abortar(self, motivo: str) -> None:
        log.error("Proceso de trabajo detenido: %s", motivo)
        plataforma.abortar_proceso(CODIGO_SALIDA_RECLAMO_PERDIDO)
