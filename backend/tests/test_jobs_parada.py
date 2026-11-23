import os
import time
from pathlib import Path

import pytest

from app.core import plataforma
from app.core.rutas import RaizDatos
from app.db.conexion import conectar
from app.db.migraciones import aplicar_migraciones
from app.jobs import service
from app.jobs.service import ReclamoPerdido
from app.jobs.worker import Worker


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


def _worker(entorno) -> Worker:
    return Worker(
        entorno["db"],
        entorno["lock"],
        RaizDatos(entorno["datos"]),
        intervalo_sondeo=0.1,
        intervalo_latido=0.3,
        gracia_cancelacion=2.0,
        intervalo_recuperacion=0.5,
    )


def _fila(entorno, trabajo_id: int):
    conexion = conectar(entorno["db"])
    try:
        return conexion.execute("SELECT * FROM trabajos WHERE id = ?", (trabajo_id,)).fetchone()
    finally:
        conexion.close()


def _esperar(condicion, segundos: float = 30.0) -> None:
    limite = time.monotonic() + segundos
    while time.monotonic() < limite:
        if condicion():
            return
        time.sleep(0.1)
    raise AssertionError("La condición no se cumplió a tiempo.")


@pytest.mark.skipif(os.name != "nt", reason="Verifica el hijo real con Job Object: Windows")
def test_parada_ordenada_con_trabajo_en_ejecucion(entorno):
    conexion = conectar(entorno["db"])
    try:
        trabajo_id = service.crear(conexion, "diagnostico_espera", {"segundos": 60}, [("audio", 0, 0, 1000)])
    finally:
        conexion.close()

    worker = _worker(entorno)
    assert worker.iniciar()
    _esperar(lambda: _fila(entorno, trabajo_id)["pid"] is not None)
    fila = _fila(entorno, trabajo_id)
    token_anterior, pid = fila["claim_token"], fila["pid"]
    assert fila["intentos"] == 1

    conexion = conectar(entorno["db"])
    try:
        assert service.marcar_segmento_procesando(conexion, trabajo_id, token_anterior, "audio", 0) is True
    finally:
        conexion.close()

    worker.detener()

    # El trabajo vuelve a cola sin consumir intento, y el proceso hijo fue terminado.
    fila = _fila(entorno, trabajo_id)
    assert fila["estado"] == "en_cola"
    assert fila["intentos"] == 0
    assert fila["claim_token"] is None
    assert fila["pid"] is None
    assert plataforma.identidad_proceso(pid) is None

    conexion = conectar(entorno["db"])
    try:
        with pytest.raises(ReclamoPerdido):
            service.latido(conexion, trabajo_id, token_anterior)
        assert service.completar(conexion, trabajo_id, token_anterior) is False
        segmento = conexion.execute(
            "SELECT estado FROM segmentos_trabajo WHERE trabajo_id = ?", (trabajo_id,)
        ).fetchone()
        assert segmento["estado"] == "pendiente"
    finally:
        conexion.close()

    # Un nuevo worker lo reclama como primer intento real.
    segundo = _worker(entorno)
    assert segundo.iniciar()
    try:
        _esperar(lambda: _fila(entorno, trabajo_id)["estado"] == "ejecutando" and _fila(entorno, trabajo_id)["pid"] is not None)
        nueva = _fila(entorno, trabajo_id)
        assert nueva["intentos"] == 1
        assert nueva["claim_token"] != token_anterior
    finally:
        segundo.detener()
