import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from app.core import plataforma
from app.core.rutas import RaizDatos
from app.db.conexion import conectar
from app.db.migraciones import aplicar_migraciones
from app.jobs import service
from app.jobs.worker import RAIZ_BACKEND, Worker

ES_WINDOWS = os.name == "nt"

CODIGO_PADRE = (
    "import sys, time\n"
    "from pathlib import Path\n"
    "from app.core.rutas import RaizDatos\n"
    "from app.jobs.worker import Worker\n"
    "w = Worker(Path(sys.argv[1]), Path(sys.argv[2]), RaizDatos(Path(sys.argv[3])),\n"
    "           intervalo_latido=0.3, intervalo_sondeo=0.1)\n"
    "w.iniciar()\n"
    "time.sleep(600)\n"
)


@pytest.fixture
def entorno(tmp_path: Path):
    datos = tmp_path / "datos"
    ruta_db = datos / "clipperai.db"
    conexion = conectar(ruta_db)
    try:
        aplicar_migraciones(conexion)
    finally:
        conexion.close()
    return {"datos": datos, "db": ruta_db, "lock": datos / "runtime" / "worker.lock"}


def _worker(entorno, **kwargs) -> Worker:
    parametros = {
        "intervalo_sondeo": 0.1,
        "intervalo_latido": 0.3,
        "gracia_cancelacion": 2.0,
        "intervalo_recuperacion": 0.5,
    }
    parametros.update(kwargs)
    return Worker(entorno["db"], entorno["lock"], RaizDatos(entorno["datos"]), **parametros)


def _consultar(entorno, trabajo_id: int) -> dict:
    conexion = conectar(entorno["db"])
    try:
        return service.consultar(conexion, trabajo_id)
    finally:
        conexion.close()


def _fila(entorno, trabajo_id: int):
    conexion = conectar(entorno["db"])
    try:
        return conexion.execute("SELECT * FROM trabajos WHERE id = ?", (trabajo_id,)).fetchone()
    finally:
        conexion.close()


def _esperar(condicion, segundos: float = 60.0, mensaje: str = "Tiempo agotado") -> None:
    limite = time.monotonic() + segundos
    while time.monotonic() < limite:
        if condicion():
            return
        time.sleep(0.1)
    raise AssertionError(mensaje)


def _esperar_estado(entorno, trabajo_id: int, estado: str, segundos: float = 60.0) -> dict:
    _esperar(
        lambda: _consultar(entorno, trabajo_id)["estado"] == estado,
        segundos,
        f"El trabajo {trabajo_id} no llegó al estado {estado}.",
    )
    return _consultar(entorno, trabajo_id)


def _crear(entorno, tipo: str, payload: dict | None = None) -> int:
    conexion = conectar(entorno["db"])
    try:
        return service.crear(conexion, tipo, payload or {})
    finally:
        conexion.close()


def _directorio(entorno, trabajo_id: int) -> Path:
    return entorno["datos"] / "work" / "trabajos" / str(trabajo_id)


def test_worker_completa_un_trabajo(entorno):
    trabajo_id = _crear(entorno, "diagnostico_espera", {"segundos": 0.5})
    worker = _worker(entorno)
    assert worker.iniciar()
    try:
        respuesta = _esperar_estado(entorno, trabajo_id, "completado")
        assert respuesta["progreso"] == 100
        assert respuesta["intentos"] == 1
        assert respuesta["error"] is None
    finally:
        worker.detener()


def test_fallo_de_tarea_queda_registrado_sin_rutas(entorno):
    trabajo_id = _crear(entorno, "diagnostico_fallo")
    worker = _worker(entorno)
    worker.iniciar()
    try:
        respuesta = _esperar_estado(entorno, trabajo_id, "fallido")
        assert "Fallo controlado de diagnóstico" in respuesta["error"]
        assert str(entorno["datos"]) not in respuesta["error"]
        assert "Traceback" not in respuesta["error"]
    finally:
        worker.detener()


def test_cancelar_trabajo_en_ejecucion_detiene_el_proceso(entorno):
    trabajo_id = _crear(entorno, "diagnostico_espera", {"segundos": 60})
    worker = _worker(entorno)
    worker.iniciar()
    try:
        _esperar(lambda: _fila(entorno, trabajo_id)["pid"] is not None, mensaje="El proceso no se registró.")
        pid = _fila(entorno, trabajo_id)["pid"]
        identidad = _fila(entorno, trabajo_id)["identidad_proceso"]
        assert plataforma.identidad_proceso(pid) == identidad

        conexion = conectar(entorno["db"])
        try:
            service.cancelar(conexion, trabajo_id)
        finally:
            conexion.close()

        respuesta = _esperar_estado(entorno, trabajo_id, "cancelado", segundos=30)
        assert respuesta["cancelacion_solicitada"] is True
        _esperar(lambda: plataforma.identidad_proceso(pid) is None, 15, "El proceso siguió vivo tras cancelar.")
    finally:
        worker.detener()


def test_cancelar_trabajo_en_cola_impide_su_ejecucion(entorno):
    trabajo_id = _crear(entorno, "diagnostico_espera", {"segundos": 0.2})
    conexion = conectar(entorno["db"])
    try:
        service.cancelar(conexion, trabajo_id)
    finally:
        conexion.close()
    worker = _worker(entorno)
    worker.iniciar()
    try:
        time.sleep(1.0)
        assert _consultar(entorno, trabajo_id)["estado"] == "cancelado"
        assert _fila(entorno, trabajo_id)["pid"] is None
    finally:
        worker.detener()


@pytest.mark.skipif(not ES_WINDOWS, reason="Verificación de descendientes con Job Object: Windows")
def test_cancelacion_mata_al_proceso_nieto(entorno):
    trabajo_id = _crear(entorno, "diagnostico_proceso_nieto", {"segundos": 60})
    worker = _worker(entorno)
    worker.iniciar()
    try:
        ruta_nieto = _directorio(entorno, trabajo_id) / "nieto.pid"
        _esperar(lambda: ruta_nieto.exists() and ruta_nieto.read_text(encoding="ascii").isdigit())
        nieto = int(ruta_nieto.read_text(encoding="ascii"))
        assert plataforma.identidad_proceso(nieto) is not None

        conexion = conectar(entorno["db"])
        try:
            service.cancelar(conexion, trabajo_id)
        finally:
            conexion.close()

        _esperar_estado(entorno, trabajo_id, "cancelado", segundos=30)
        _esperar(lambda: plataforma.identidad_proceso(nieto) is None, 15, "El nieto quedó huérfano.")
    finally:
        worker.detener()


@pytest.mark.skipif(not ES_WINDOWS, reason="Verificación de descendientes con Job Object: Windows")
def test_completar_no_deja_procesos_huerfanos(entorno):
    trabajo_id = _crear(entorno, "diagnostico_proceso_nieto", {"segundos": 1})
    worker = _worker(entorno)
    worker.iniciar()
    try:
        _esperar_estado(entorno, trabajo_id, "completado")
        ruta_nieto = _directorio(entorno, trabajo_id) / "nieto.pid"
        nieto = int(ruta_nieto.read_text(encoding="ascii"))
        _esperar(lambda: plataforma.identidad_proceso(nieto) is None, 15, "El nieto sobrevivió al trabajo.")
    finally:
        worker.detener()


def test_un_solo_trabajo_pesado_a_la_vez(entorno):
    ids = [_crear(entorno, "diagnostico_espera", {"segundos": 0.4}) for _ in range(3)]
    maximo_simultaneo = 0
    detener_muestreo = threading.Event()

    def muestrear() -> None:
        nonlocal maximo_simultaneo
        conexion = conectar(entorno["db"])
        try:
            while not detener_muestreo.is_set():
                cuenta = conexion.execute("SELECT COUNT(*) FROM trabajos WHERE estado = 'ejecutando'").fetchone()[0]
                maximo_simultaneo = max(maximo_simultaneo, cuenta)
                time.sleep(0.02)
        finally:
            conexion.close()

    muestreo = threading.Thread(target=muestrear, daemon=True)
    muestreo.start()
    worker = _worker(entorno)
    worker.iniciar()
    try:
        for trabajo_id in ids:
            _esperar_estado(entorno, trabajo_id, "completado")
    finally:
        detener_muestreo.set()
        muestreo.join(5)
        worker.detener()
    assert maximo_simultaneo == 1
    assert [_consultar(entorno, i)["intentos"] for i in ids] == [1, 1, 1]


def test_segundo_worker_no_arranca_mientras_el_primero_vive(entorno):
    primero = _worker(entorno)
    segundo = _worker(entorno)
    assert primero.iniciar() is True
    try:
        assert segundo.iniciar() is False
        assert segundo.activo() is False
    finally:
        primero.detener()
    assert segundo.iniciar() is True
    segundo.detener()


def test_recuperacion_sin_pid_espera_al_umbral_de_latido(entorno):
    conexion = conectar(entorno["db"])
    try:
        trabajo_id = service.crear(conexion, "diagnostico_espera", {"segundos": 0.2})
        assert service.reclamar_siguiente(conexion, "h" * 32) == trabajo_id
        conexion.execute("UPDATE trabajos SET latido = ? WHERE id = ?", (service.ahora_iso(), trabajo_id))
        conexion.commit()
    finally:
        conexion.close()

    worker = _worker(entorno, umbral_latido=2.0)
    worker.iniciar()
    try:
        time.sleep(1.5)
        assert _consultar(entorno, trabajo_id)["estado"] == "ejecutando"

        _esperar(lambda: _consultar(entorno, trabajo_id)["estado"] == "completado", 30, "No se recuperó el trabajo.")
        assert _consultar(entorno, trabajo_id)["intentos"] == 2
    finally:
        worker.detener()


@pytest.mark.skipif(not ES_WINDOWS, reason="El escenario de caída usa taskkill y Job Objects: Windows")
def test_caida_del_backend_mata_al_hijo_y_se_recupera_el_trabajo(entorno):
    trabajo_id = _crear(entorno, "diagnostico_espera", {"segundos": 60})
    ruta_lock = entorno["lock"]
    dueno = subprocess.Popen(
        [sys.executable, "-c", CODIGO_PADRE, str(entorno["db"]), str(ruta_lock), str(entorno["datos"])],
        cwd=RAIZ_BACKEND,
    )
    try:
        _esperar(lambda: _fila(entorno, trabajo_id)["pid"] is not None, 30, "El proceso hijo no se registró.")
        fila = _fila(entorno, trabajo_id)
        pid_hijo, identidad_hijo = fila["pid"], fila["identidad_proceso"]
        assert plataforma.identidad_proceso(pid_hijo) == identidad_hijo

        # Caída brusca del backend: se termina todo su árbol de procesos.
        subprocess.run(["taskkill", "/PID", str(dueno.pid), "/T", "/F"], capture_output=True, check=False)
        dueno.wait(15)
        _esperar(lambda: plataforma.identidad_proceso(pid_hijo) is None, 15, "El hijo sobrevivió a la caída.")

        # Tras la caída, el bloqueo debe estar libre.
        conexion = conectar(entorno["db"])
        conexion.execute(
            "UPDATE trabajos SET payload_json = '{\"segundos\": 0.2}' WHERE id = ?", (trabajo_id,)
        )
        conexion.commit()
        conexion.close()
        recuperado = _worker(entorno)
        assert recuperado.iniciar() is True
        try:
            respuesta = _esperar_estado(entorno, trabajo_id, "completado", segundos=60)
            assert respuesta["intentos"] == 2
        finally:
            recuperado.detener()
    finally:
        if dueno.poll() is None:
            subprocess.run(["taskkill", "/PID", str(dueno.pid), "/T", "/F"], capture_output=True, check=False)
