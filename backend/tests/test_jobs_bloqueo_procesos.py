import subprocess
import sys
from pathlib import Path

import pytest

from app.core.plataforma import BloqueoExclusivo

RAIZ_BACKEND = Path(__file__).resolve().parents[1]

# Controlador de un proceso independiente. Lee órdenes por stdin y responde una línea por orden.
# intentar: intenta adquirir el bloqueo, si aún no lo tiene. liberar: lo suelta. salir: termina.
CODIGO_CONTROLADOR = """
import sys
from pathlib import Path
from app.core.plataforma import BloqueoExclusivo

ruta = Path(sys.argv[1])
bloqueo = None
for linea in sys.stdin:
    orden = linea.strip()
    if orden == "intentar":
        if bloqueo is None:
            bloqueo = BloqueoExclusivo.adquirir(ruta)
        print("ADQUIRIDO" if bloqueo is not None else "OCUPADO", flush=True)
    elif orden == "liberar":
        if bloqueo is not None:
            bloqueo.liberar()
            bloqueo = None
        print("LIBERADO", flush=True)
    elif orden == "salir":
        break
if bloqueo is not None:
    bloqueo.liberar()
"""


def _matar_arbol(proceso: subprocess.Popen) -> None:
    """En Windows, el intérprete de venv es un lanzador: hay que terminar también su hijo real."""
    if proceso.poll() is not None:
        return
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/PID", str(proceso.pid), "/T", "/F"], capture_output=True, check=False)
    else:
        proceso.kill()
    proceso.wait(15)


class Controlador:
    def __init__(self, ruta: Path) -> None:
        self.proceso = subprocess.Popen(
            [sys.executable, "-c", CODIGO_CONTROLADOR, str(ruta)],
            cwd=RAIZ_BACKEND,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    def orden(self, texto: str) -> str:
        self.proceso.stdin.write(texto + "\n")
        self.proceso.stdin.flush()
        respuesta = self.proceso.stdout.readline().strip()
        assert respuesta, f"El proceso no respondió a '{texto}': {self.proceso.stderr.read()}"
        return respuesta

    def cerrar(self) -> None:
        try:
            if self.proceso.poll() is None:
                self.proceso.stdin.write("salir\n")
                self.proceso.stdin.flush()
                self.proceso.wait(15)
        except (BrokenPipeError, subprocess.TimeoutExpired):
            pass
        finally:
            _matar_arbol(self.proceso)
            for flujo in (self.proceso.stdin, self.proceso.stdout, self.proceso.stderr):
                if flujo is not None:
                    flujo.close()


def test_dos_procesos_independientes_se_excluyen_en_worker_lock(tmp_path):
    ruta = tmp_path / "runtime" / "worker.lock"
    primero = Controlador(ruta)
    segundo = Controlador(ruta)
    try:
        assert primero.orden("intentar") == "ADQUIRIDO"

        # Mientras el primero mantiene el bloqueo, el segundo no puede adquirirlo, aunque lo intente varias veces.
        for _ in range(3):
            assert segundo.orden("intentar") == "OCUPADO"

        assert primero.orden("liberar") == "LIBERADO"
        assert segundo.orden("intentar") == "ADQUIRIDO"

        # Tras la liberación, el primero tampoco puede volver a adquirirlo.
        assert primero.orden("intentar") == "OCUPADO"
        assert segundo.orden("liberar") == "LIBERADO"
        assert primero.orden("intentar") == "ADQUIRIDO"
    finally:
        primero.cerrar()
        segundo.cerrar()

    # Tras cerrar ambos procesos, el bloqueo debe estar libre y no quedar retenido.
    verificacion = BloqueoExclusivo.adquirir(ruta)
    assert verificacion is not None
    verificacion.liberar()
    assert primero.proceso.poll() is not None
    assert segundo.proceso.poll() is not None


def test_bloqueo_de_proceso_terminado_por_la_fuerza_se_libera(tmp_path):
    ruta = tmp_path / "runtime" / "worker.lock"
    dueno = Controlador(ruta)
    try:
        assert dueno.orden("intentar") == "ADQUIRIDO"
        _matar_arbol(dueno.proceso)
    finally:
        dueno.cerrar()
    recuperado = BloqueoExclusivo.adquirir(ruta)
    assert recuperado is not None
    recuperado.liberar()
