import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from app.core import plataforma

ES_WINDOWS = os.name == "nt"
RAIZ_BACKEND = Path(__file__).resolve().parents[1]

CODIGO_NIETO = (
    "import os, pathlib, sys, time\n"
    "pathlib.Path(sys.argv[1]).write_text(str(os.getpid()), encoding='ascii')\n"
    "time.sleep(600)\n"
)
CODIGO_PADRE_CON_NIETO = (
    "import subprocess, sys, time\n"
    "subprocess.Popen([sys.executable, '-c', sys.argv[2], sys.argv[1]])\n"
    "time.sleep(600)\n"
)


def _esperar(condicion, segundos: float = 15.0) -> None:
    limite = time.monotonic() + segundos
    while time.monotonic() < limite:
        if condicion():
            return
        time.sleep(0.1)
    raise AssertionError("La condición no se cumplió a tiempo.")


def _leer_pid(ruta: Path) -> int:
    _esperar(lambda: ruta.exists() and ruta.read_text(encoding="ascii").strip().isdigit())
    return int(ruta.read_text(encoding="ascii"))


def test_bloqueo_exclusivo_se_libera(tmp_path):
    ruta = tmp_path / "worker.lock"
    primero = plataforma.BloqueoExclusivo.adquirir(ruta)
    assert primero is not None
    assert plataforma.BloqueoExclusivo.adquirir(ruta) is None
    primero.liberar()
    segundo = plataforma.BloqueoExclusivo.adquirir(ruta)
    assert segundo is not None
    segundo.liberar()


def test_bloqueo_se_libera_ante_excepcion(tmp_path):
    ruta = tmp_path / "worker.lock"
    with pytest.raises(RuntimeError):
        with plataforma.BloqueoExclusivo.adquirir(ruta):
            raise RuntimeError("fallo simulado")
    recuperado = plataforma.BloqueoExclusivo.adquirir(ruta)
    assert recuperado is not None
    recuperado.liberar()


def test_identidad_de_proceso_propio_es_estable():
    primera = plataforma.identidad_proceso(os.getpid())
    segunda = plataforma.identidad_proceso(os.getpid())
    assert primera is not None
    assert primera == segunda


def test_identidad_de_proceso_terminado_es_none():
    proceso = subprocess.Popen([sys.executable, "-c", "pass"])
    proceso.wait(15)
    _esperar(lambda: plataforma.identidad_proceso(proceso.pid) is None)
    assert plataforma.identidad_proceso(proceso.pid) is None


def test_terminar_verificado_rechaza_identidad_distinta():
    proceso = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        identidad = plataforma.identidad_proceso(proceso.pid)
        assert identidad is not None
        assert plataforma.terminar_proceso_verificado(proceso.pid, "0") is False
        assert proceso.poll() is None
        assert plataforma.terminar_proceso_verificado(proceso.pid, identidad) is True
        proceso.wait(15)
    finally:
        if proceso.poll() is None:
            proceso.kill()


def test_grupo_termina_al_nieto(tmp_path):
    ruta_pid = tmp_path / "nieto.pid"
    grupo = plataforma.GrupoProcesos()
    proceso = grupo.iniciar(
        [sys.executable, "-c", CODIGO_PADRE_CON_NIETO, str(ruta_pid), CODIGO_NIETO],
        cwd=RAIZ_BACKEND,
    )
    try:
        nieto = _leer_pid(ruta_pid)
        assert plataforma.identidad_proceso(nieto) is not None
        grupo.terminar()
        proceso.wait(15)
        _esperar(lambda: plataforma.identidad_proceso(nieto) is None)
    finally:
        grupo.cerrar()
        if proceso.poll() is None:
            proceso.kill()


def test_cerrar_grupo_limpia_descendientes_que_siguen_vivos(tmp_path):
    """Un proceso que sale dejando un nieto vivo no debe dejar huérfanos al cerrar el grupo."""
    ruta_pid = tmp_path / "nieto.pid"
    grupo = plataforma.GrupoProcesos()
    proceso = grupo.iniciar(
        [sys.executable, "-c", CODIGO_PADRE_CON_NIETO, str(ruta_pid), CODIGO_NIETO],
        cwd=RAIZ_BACKEND,
    )
    try:
        nieto = _leer_pid(ruta_pid)
        proceso.kill()
        proceso.wait(15)
        grupo.cerrar()
        _esperar(lambda: plataforma.identidad_proceso(nieto) is None)
    finally:
        grupo.cerrar()
        if proceso.poll() is None:
            proceso.kill()


@pytest.mark.skipif(not ES_WINDOWS, reason="Job Object solo existe en Windows")
def test_job_object_mata_al_nieto_si_el_padre_muere_sin_cerrar(tmp_path):
    """Caso de caída: el proceso dueño del grupo desaparece y el sistema debe cerrar el Job Object."""
    ruta_pid = tmp_path / "nieto.pid"
    # El intérprete de venv es un lanzador que crea el intérprete real como hijo. La caída se simula
    # terminando el árbol completo, igual que un cierre brusco del backend.
    dueno = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import sys, time\n"
            "from app.core import plataforma\n"
            "grupo = plataforma.GrupoProcesos()\n"
            "grupo.iniciar([sys.executable, '-c', sys.argv[2], sys.argv[1], sys.argv[4]], cwd=sys.argv[3])\n"
            "time.sleep(600)\n",
            str(ruta_pid),
            CODIGO_PADRE_CON_NIETO,
            str(RAIZ_BACKEND),
            CODIGO_NIETO,
        ],
        cwd=RAIZ_BACKEND,
    )
    try:
        nieto = _leer_pid(ruta_pid)
        subprocess.run(["taskkill", "/PID", str(dueno.pid), "/T", "/F"], capture_output=True, check=False)
        dueno.wait(15)
        _esperar(lambda: plataforma.identidad_proceso(nieto) is None)
    finally:
        if dueno.poll() is None:
            subprocess.run(["taskkill", "/PID", str(dueno.pid), "/T", "/F"], capture_output=True, check=False)


@pytest.mark.skipif(ES_WINDOWS, reason="Rama POSIX: se ejecuta solo fuera de Windows, no verificada en macOS aquí")
def test_posix_grupo_de_procesos_es_lider_de_sesion(tmp_path):
    grupo = plataforma.GrupoProcesos()
    proceso = grupo.iniciar([sys.executable, "-c", "import time; time.sleep(60)"], cwd=RAIZ_BACKEND)
    try:
        assert os.getpgid(proceso.pid) == proceso.pid
    finally:
        grupo.terminar()
        proceso.wait(15)
        grupo.cerrar()
