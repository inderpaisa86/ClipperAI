import subprocess
import sys
import time
from pathlib import Path

import pytest

from app.core import plataforma
from app.db.conexion import conectar
from app.db.migraciones import aplicar_migraciones
from app.jobs import service
from app.jobs.contexto import CODIGO_SALIDA_RECLAMO_PERDIDO, ContextoTrabajo
from app.jobs.service import ReclamoPerdido, TrabajoCancelado

RAIZ_BACKEND = Path(__file__).resolve().parents[1]


@pytest.fixture
def base(tmp_path: Path):
    ruta = tmp_path / "datos" / "clipperai.db"
    conexion = conectar(ruta)
    aplicar_migraciones(conexion)
    yield {"ruta": ruta, "conexion": conexion, "directorio": tmp_path / "datos" / "work" / "trabajos"}
    conexion.close()


def _esperar(condicion, segundos: float = 10.0) -> None:
    limite = time.monotonic() + segundos
    while time.monotonic() < limite:
        if condicion():
            return
        time.sleep(0.02)
    raise AssertionError("La condición no se cumplió a tiempo.")


def _trabajo_reclamado(base, token: str) -> int:
    trabajo_id = service.crear(base["conexion"], "diagnostico_espera", {})
    assert service.reclamar_siguiente(base["conexion"], token) == trabajo_id
    return trabajo_id


def _contexto(base, trabajo_id: int, token: str, intervalo: float = 0.05) -> ContextoTrabajo:
    return ContextoTrabajo(
        base["ruta"], base["conexion"], trabajo_id, token, {}, base["directorio"] / str(trabajo_id), intervalo
    )


def test_hilo_de_latidos_renueva_el_latido(base):
    token = "1" * 32
    trabajo_id = _trabajo_reclamado(base, token)
    latido_inicial = base["conexion"].execute("SELECT latido FROM trabajos WHERE id = ?", (trabajo_id,)).fetchone()[0]
    contexto = _contexto(base, trabajo_id, token)
    contexto.iniciar_latidos()
    try:
        _esperar(
            lambda: base["conexion"].execute("SELECT latido FROM trabajos WHERE id = ?", (trabajo_id,)).fetchone()[0]
            != latido_inicial
        )
    finally:
        contexto.cerrar()


def test_hilo_de_latidos_detecta_cancelacion(base):
    token = "2" * 32
    trabajo_id = _trabajo_reclamado(base, token)
    contexto = _contexto(base, trabajo_id, token)
    contexto.iniciar_latidos()
    try:
        otra = conectar(base["ruta"])
        try:
            service.cancelar(otra, trabajo_id)
        finally:
            otra.close()
        _esperar(contexto.cancelado)
        with pytest.raises(TrabajoCancelado):
            contexto.verificar_cancelacion()
    finally:
        contexto.cerrar()


def test_progreso_con_token_invalidado_lanza_reclamo_perdido(base):
    token = "3" * 32
    trabajo_id = _trabajo_reclamado(base, token)
    contexto = _contexto(base, trabajo_id, token)
    service.reencolar_interrumpido(base["conexion"], trabajo_id, token, max_intentos=3)
    with pytest.raises(ReclamoPerdido):
        contexto.progreso(50)


def test_hilo_aborta_si_el_reclamo_se_pierde(base, monkeypatch):
    llamadas: list[int] = []
    monkeypatch.setattr(plataforma, "abortar_proceso", lambda codigo: llamadas.append(codigo))
    token = "4" * 32
    trabajo_id = _trabajo_reclamado(base, token)
    contexto = _contexto(base, trabajo_id, token)
    service.reencolar_interrumpido(base["conexion"], trabajo_id, token, max_intentos=3)
    contexto.iniciar_latidos()
    try:
        _esperar(lambda: len(llamadas) >= 1)
        assert llamadas[0] == CODIGO_SALIDA_RECLAMO_PERDIDO
    finally:
        contexto.cerrar()


def test_hilo_aborta_si_el_proceso_padre_cambia(base, monkeypatch):
    llamadas: list[int] = []
    monkeypatch.setattr(plataforma, "abortar_proceso", lambda codigo: llamadas.append(codigo))
    token = "5" * 32
    trabajo_id = _trabajo_reclamado(base, token)
    contexto = _contexto(base, trabajo_id, token)
    contexto._padre = -1  # Simula que el padre original ya no existe.
    contexto.iniciar_latidos()
    try:
        _esperar(lambda: len(llamadas) >= 1)
        assert llamadas[0] == CODIGO_SALIDA_RECLAMO_PERDIDO
    finally:
        contexto.cerrar()


@pytest.mark.skipif(sys.platform != "win32", reason="Prueba de extremo a extremo verificada solo en Windows")
def test_proceso_real_sale_con_codigo_3_al_perder_el_reclamo(base):
    token = "6" * 32
    trabajo_id = _trabajo_reclamado(base, token)
    proceso = subprocess.Popen(
        [
            sys.executable, "-m", "app.jobs.ejecutar",
            str(trabajo_id), token, str(base["ruta"]), str(base["directorio"] / str(trabajo_id)), "0.1",
        ],
        cwd=RAIZ_BACKEND,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _esperar(lambda: base["conexion"].execute("SELECT pid FROM trabajos WHERE id = ?", (trabajo_id,)).fetchone()[0] is not None, 30)
        # Quita el reclamo al proceso en ejecución, como si otro worker lo hubiera reasignado.
        service.reencolar_interrumpido(base["conexion"], trabajo_id, token, max_intentos=3)
        codigo = proceso.wait(30)
        assert codigo == CODIGO_SALIDA_RECLAMO_PERDIDO
    finally:
        if proceso.poll() is None:
            subprocess.run(["taskkill", "/PID", str(proceso.pid), "/T", "/F"], capture_output=True, check=False)
            proceso.wait(15)
