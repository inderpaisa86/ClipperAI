"""Registro de tipos de trabajo.

Los tipos `diagnostico_*` solo sirven para verificar la infraestructura. No se crean desde la API
y no acceden a archivos del usuario. Los módulos de análisis registrarán sus tipos aquí en las etapas siguientes.
"""

import subprocess
import sys
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.jobs.contexto import ContextoTrabajo

Tarea = Callable[[dict[str, Any], "ContextoTrabajo"], None]

SEGUNDOS_MAXIMOS = 60.0
# El PID se publica con un temporal y os.replace. Quien lo lee ve el archivo completo o no lo ve.
CODIGO_NIETO = (
    "import os, pathlib, sys, time\n"
    "destino = pathlib.Path(sys.argv[1])\n"
    "temporal = destino.with_name(destino.name + '.tmp')\n"
    "temporal.write_text(str(os.getpid()), encoding='ascii')\n"
    "os.replace(temporal, destino)\n"
    "time.sleep(600)\n"
)


def _segundos(payload: dict[str, Any], valor_por_defecto: float) -> float:
    try:
        segundos = float(payload.get("segundos", valor_por_defecto))
    except (TypeError, ValueError) as error:
        raise ValueError("El valor de segundos no es válido.") from error
    return min(max(segundos, 0.0), SEGUNDOS_MAXIMOS)


def _espera(payload: dict[str, Any], ctx: "ContextoTrabajo") -> None:
    segundos = _segundos(payload, 1.0)
    inicio = time.monotonic()
    progreso_anterior = -1
    while True:
        ctx.verificar_cancelacion()
        transcurrido = time.monotonic() - inicio
        if transcurrido >= segundos:
            return
        porcentaje = int(100 * transcurrido / segundos) if segundos > 0 else 100
        if porcentaje != progreso_anterior:
            ctx.progreso(porcentaje)
            progreso_anterior = porcentaje
        time.sleep(0.05)


def _fallo(payload: dict[str, Any], ctx: "ContextoTrabajo") -> None:
    raise RuntimeError("Fallo controlado de diagnóstico.")


def _proceso_nieto(payload: dict[str, Any], ctx: "ContextoTrabajo") -> None:
    """Lanza un proceso descendiente que anota su PID. Sirve para probar que no queda huérfano."""
    ctx.directorio.mkdir(parents=True, exist_ok=True)
    subprocess.Popen(
        [sys.executable, "-c", CODIGO_NIETO, str(ctx.directorio / "nieto.pid")],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    _espera(payload, ctx)


REGISTRO: dict[str, Tarea] = {
    "diagnostico_espera": _espera,
    "diagnostico_fallo": _fallo,
    "diagnostico_proceso_nieto": _proceso_nieto,
}


# Gancho de cierre sin éxito: (conexión, trabajo_id, estado, error). Estado es `cancelado` o `fallido`.
GanchoTerminar = Callable[[Any, int, str, str | None], None]
GANCHOS_TERMINAR: dict[str, GanchoTerminar] = {}


def registrar(tipo: str, tarea: Tarea, al_terminar: GanchoTerminar | None = None) -> None:
    """Registra un tipo de trabajo. Lo llama el arranque de la aplicación, no los módulos.

    `al_terminar` recibe (conexión, trabajo_id, estado, error). `jobs` lo llama dentro de la misma transacción
    que deja el trabajo en `cancelado` o `fallido`, sea cual sea el proceso que cierra el trabajo: quien pide
    la cancelación, el proceso del trabajo, el supervisor o la recuperación. Así el módulo dueño de un resultado
    lo cierra sin depender del proceso hijo. `jobs` no importa a los módulos de análisis.
    """
    REGISTRO[tipo] = tarea
    if al_terminar is not None:
        GANCHOS_TERMINAR[tipo] = al_terminar


def gancho_terminar(tipo: str) -> GanchoTerminar | None:
    return GANCHOS_TERMINAR.get(tipo)


def existe(tipo: str) -> bool:
    return tipo in REGISTRO


def obtener(tipo: str) -> Tarea | None:
    return REGISTRO.get(tipo)
