"""Worker de trabajos. Un solo worker activo por directorio de datos y un solo trabajo pesado a la vez.

Garantías:
- El bloqueo `worker.lock` impide que dos procesos ejecuten el worker.
- El reclamo es atómico en SQLite y no permite reclamar si ya hay un trabajo en ejecución.
- Cada resultado exige el `claim_token`, así que un proceso que perdió el reclamo no puede escribir.
- Un proceso solo se termina si su identidad (PID y hora de creación) coincide con la registrada.
"""

import logging
import secrets
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

from app.core import plataforma
from app.core.rutas import RaizDatos
from app.db.conexion import conectar
from app.jobs import service

log = logging.getLogger("clipperai.jobs")

RAIZ_BACKEND = Path(__file__).resolve().parents[2]
ESPERA_TERMINACION_SEGUNDOS = 10.0
GRACIA_FIN_NORMAL_SEGUNDOS = 5.0


class Worker:
    def __init__(
        self,
        ruta_db: Path,
        ruta_bloqueo: Path,
        raiz_datos: RaizDatos,
        *,
        intervalo_sondeo: float = 0.5,
        intervalo_latido: float = 10.0,
        gracia_cancelacion: float = 15.0,
        umbral_latido: float = 60.0,
        intervalo_recuperacion: float = 10.0,
        max_intentos: int = 3,
        ejecutable_python: str | None = None,
    ) -> None:
        self._ruta_db = ruta_db
        self._ruta_bloqueo = ruta_bloqueo
        self._raiz_datos = raiz_datos
        self._intervalo_sondeo = intervalo_sondeo
        self._intervalo_latido = intervalo_latido
        self._gracia_cancelacion = gracia_cancelacion
        self._umbral_latido = umbral_latido
        self._intervalo_recuperacion = intervalo_recuperacion
        self._max_intentos = max_intentos
        self._python = ejecutable_python or sys.executable
        self._parar = threading.Event()
        self._hilo: threading.Thread | None = None
        self._bloqueo: plataforma.BloqueoExclusivo | None = None

    def iniciar(self) -> bool:
        """Adquiere el bloqueo y arranca el hilo. Devuelve False si otro worker ya está activo."""
        if self._hilo is not None:
            return True
        bloqueo = plataforma.BloqueoExclusivo.adquirir(self._ruta_bloqueo)
        if bloqueo is None:
            log.info("Otro proceso tiene el worker de trabajos activo.")
            return False
        self._bloqueo = bloqueo
        self._parar.clear()
        self._hilo = threading.Thread(target=self._bucle, name="clipperai-worker", daemon=True)
        self._hilo.start()
        return True

    def detener(self, espera_segundos: float = 60.0) -> None:
        """Pide detener el worker. Un trabajo en curso se termina y vuelve a cola, sin contar como fallo."""
        self._parar.set()
        if self._hilo is not None:
            self._hilo.join(espera_segundos)
            self._hilo = None

    def activo(self) -> bool:
        return self._hilo is not None and self._hilo.is_alive()

    # -- Bucle principal --------------------------------------------------

    def _bucle(self) -> None:
        conexion = conectar(self._ruta_db)
        try:
            self._recuperar(conexion)
            ultima_recuperacion = time.monotonic()
            while not self._parar.is_set():
                if time.monotonic() - ultima_recuperacion >= self._intervalo_recuperacion:
                    self._recuperar(conexion)
                    ultima_recuperacion = time.monotonic()
                if not self._ejecutar_siguiente(conexion):
                    self._parar.wait(self._intervalo_sondeo)
        except Exception as error:  # noqa: BLE001 - el hilo no debe caer en silencio
            log.error("El worker se detuvo por un error (%s).", type(error).__name__)
        finally:
            conexion.close()
            if self._bloqueo is not None:
                self._bloqueo.liberar()
                self._bloqueo = None

    def _ejecutar_siguiente(self, conexion: Any) -> bool:
        token = secrets.token_hex(16)
        trabajo_id = service.reclamar_siguiente(conexion, token)
        if trabajo_id is None:
            return False
        log.info("Trabajo %s reclamado.", trabajo_id)
        self._ejecutar(conexion, trabajo_id, token)
        return True

    # -- Ejecución de un trabajo ---------------------------------------------

    def _ejecutar(self, conexion: Any, trabajo_id: int, token: str) -> None:
        directorio = self._raiz_datos.resolver(f"work/trabajos/{trabajo_id}")
        grupo = plataforma.GrupoProcesos()
        argumentos = [
            self._python,
            "-m",
            "app.jobs.ejecutar",
            str(trabajo_id),
            token,
            str(self._ruta_db),
            str(directorio),
            str(self._intervalo_latido),
        ]
        try:
            proceso = grupo.iniciar(argumentos, cwd=RAIZ_BACKEND)
        except OSError:
            grupo.cerrar()
            service.fallar(conexion, trabajo_id, token, "No se pudo iniciar el proceso del trabajo.")
            return

        try:
            codigo, deteniendo = self._supervisar(conexion, trabajo_id, token, proceso, grupo)
        finally:
            grupo.terminar()
            try:
                proceso.wait(ESPERA_TERMINACION_SEGUNDOS)
            except subprocess.TimeoutExpired:
                log.error("El proceso del trabajo %s no terminó tras la orden de cierre.", trabajo_id)
            grupo.cerrar()

        resultado = service.cerrar_tras_proceso(
            conexion, trabajo_id, token, codigo, deteniendo
        )
        log.info("Trabajo %s: %s.", trabajo_id, resultado)

    def _supervisar(
        self,
        conexion: Any,
        trabajo_id: int,
        token: str,
        proceso: subprocess.Popen,
        grupo: plataforma.GrupoProcesos,
    ) -> tuple[int | None, bool]:
        """Espera al proceso y aplica cancelación y parada. Devuelve (código, si se detuvo por parada)."""
        inicio_cancelacion: float | None = None
        inicio_sin_reclamo: float | None = None
        deteniendo = False
        while True:
            codigo = proceso.poll()
            if codigo is not None:
                return codigo, deteniendo
            if self._parar.is_set() and not deteniendo:
                deteniendo = True
                grupo.terminar()

            control = service.leer_control(conexion, trabajo_id, token)
            ahora = time.monotonic()
            if control is None:
                # El proceso ya cerró su estado, o perdió el reclamo. Le damos un margen para salir.
                inicio_sin_reclamo = inicio_sin_reclamo or ahora
                if ahora - inicio_sin_reclamo >= GRACIA_FIN_NORMAL_SEGUNDOS:
                    grupo.terminar()
            elif control["cancelacion_solicitada"]:
                inicio_cancelacion = inicio_cancelacion or ahora
                if ahora - inicio_cancelacion >= self._gracia_cancelacion:
                    grupo.terminar()
            self._parar.wait(self._intervalo_sondeo)

    # -- Recuperación de trabajos interrumpidos --------------------------------

    def _recuperar(self, conexion: Any) -> None:
        """Revisa los trabajos marcados como ejecutándose. Solo se devuelven a cola los que no tienen proceso vivo."""
        for fila in service.listar_ejecucion(conexion):
            pid = fila["pid"]
            identidad = fila["identidad_proceso"]
            if pid is not None and identidad is not None:
                if plataforma.identidad_proceso(pid) == identidad:
                    # Proceso vivo y confirmado: se termina antes de reencolar.
                    plataforma.terminar_proceso_verificado(pid, identidad)
                    if self._esperar_fin(pid, identidad):
                        log.error("El proceso de un trabajo interrumpido sigue vivo y no se pudo terminar.")
                        continue
                # Si la identidad ya no coincide, el proceso original terminó: se reencola de inmediato.
            elif not service.latido_vencido(fila["latido"], self._umbral_latido):
                # Sin PID registrado no hay forma de confirmar el proceso. Se espera al umbral de latido.
                continue
            resultado = service.reencolar_interrumpido(
                conexion, fila["id"], fila["claim_token"], self._max_intentos
            )
            log.info("Trabajo %s tras interrupción: %s.", fila["id"], resultado)

    def _esperar_fin(self, pid: int, identidad: str) -> bool:
        """True si el proceso sigue vivo tras esperar."""
        limite = time.monotonic() + ESPERA_TERMINACION_SEGUNDOS
        while time.monotonic() < limite:
            if plataforma.identidad_proceso(pid) != identidad:
                return False
            time.sleep(0.2)
        return True
