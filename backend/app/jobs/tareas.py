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
CODIGO_NIETO = (
    "import os, pathlib, sys, time\n"
    "pathlib.Path(sys.argv[1]).write_text(str(os.getpid()), encoding='ascii')\n"
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


def existe(tipo: str) -> bool:
    return tipo in REGISTRO


def obtener(tipo: str) -> Tarea | None:
    return REGISTRO.get(tipo)
