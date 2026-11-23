"""Cancelación de un análisis con worker y proceso hijo reales.

El audio dura dos horas para que el análisis siga en curso cuando se cancela. La prueba espera a que el
trabajo esté ejecutando con progreso (al menos 10 %), cancela y comprueba los estados finales, la terminación
del hijo y que no quedan señales ni registros huérfanos. Requiere FFmpeg y FFprobe.
"""

import subprocess
import time
from pathlib import Path

import pytest

from app.composicion import registrar
from app.core import plataforma
from app.core.rutas import RaizDatos
from app.db.conexion import conectar
from app.db.migraciones import aplicar_migraciones
from app.jobs import service as trabajos
from app.jobs.worker import Worker
from app.modules.audio import service as audio
from app.modules.projects import service as proyectos
from app.modules.projects.schemas import ProyectoCrear
from app.modules.videos import repository as videos_repo
from tests.conftest import requiere_ffmpeg

pytestmark = requiere_ffmpeg

DURACION_S = 7200


@pytest.fixture(scope="module")
def audio_largo(tmp_path_factory) -> Path:
    destino = tmp_path_factory.mktemp("medios") / "dos_horas.m4a"
    comando = [
        "ffmpeg", "-v", "error", "-y",
        "-f", "lavfi", "-i", f"sine=frequency=440:duration={DURACION_S}",
        "-c:a", "aac", str(destino),
    ]
    subprocess.run(comando, check=True, capture_output=True)
    return destino


@pytest.fixture
def base(tmp_path, audio_largo):
    registrar()
    datos = tmp_path / "datos"
    ruta_db = datos / "clipperai.db"
    conexion = conectar(ruta_db)
    try:
        aplicar_migraciones(conexion)
        proyecto = proyectos.crear(conexion, ProyectoCrear(nombre="Cancelación real")).id
        video = videos_repo.insertar(
            conexion,
            {
                "proyecto_id": proyecto,
                "nombre": audio_largo.name,
                "ruta_original": str(audio_largo),
                "tamano_bytes": audio_largo.stat().st_size,
                "duracion_segundos": float(DURACION_S),
                "ancho": 16,
                "alto": 16,
                "fps": 1.0,
                "codec_video": "h264",
                "codec_audio": "aac",
                "formato": "mp4",
            },
        )
    finally:
        conexion.close()
    return {"db": ruta_db, "datos": datos, "lock": datos / "runtime" / "worker.lock", "video": video}


def _worker(base, gracia: float) -> Worker:
    return Worker(
        base["db"],
        base["lock"],
        RaizDatos(base["datos"]),
        intervalo_sondeo=0.1,
        intervalo_latido=0.3,
        gracia_cancelacion=gracia,
        intervalo_recuperacion=0.5,
    )


def _esperar(condicion, segundos: float, mensaje: str) -> None:
    limite = time.monotonic() + segundos
    while time.monotonic() < limite:
        if condicion():
            return
        time.sleep(0.1)
    raise AssertionError(mensaje)


def _fila_trabajo(base, trabajo_id: int):
    conexion = conectar(base["db"])
    try:
        return conexion.execute("SELECT * FROM trabajos WHERE id = ?", (trabajo_id,)).fetchone()
    finally:
        conexion.close()


def _estado_analisis(base) -> str:
    conexion = conectar(base["db"])
    try:
        return conexion.execute(
            "SELECT estado FROM analisis WHERE video_id = ? AND analizador = 'audio'", (base["video"],)
        ).fetchone()["estado"]
    finally:
        conexion.close()


def _iniciar(base) -> int:
    conexion = conectar(base["db"])
    try:
        return audio.iniciar_analisis(conexion, base["video"])
    finally:
        conexion.close()


def _ejecutando_con_progreso(base, trabajo_id: int) -> bool:
    fila = _fila_trabajo(base, trabajo_id)
    return fila["estado"] == "ejecutando" and fila["progreso"] >= 10 and fila["pid"] is not None


def _comprobar_sin_residuos(base) -> None:
    conexion = conectar(base["db"])
    try:
        senales = conexion.execute(
            "SELECT COUNT(*) FROM senales s JOIN analisis a ON a.id = s.analisis_id WHERE a.video_id = ?",
            (base["video"],),
        ).fetchone()[0]
        fotogramas = conexion.execute(
            "SELECT COUNT(*) FROM fotogramas f JOIN analisis a ON a.id = f.analisis_id WHERE a.video_id = ?",
            (base["video"],),
        ).fetchone()[0]
        huerfanas = conexion.execute(
            "SELECT COUNT(*) FROM senales s LEFT JOIN analisis a ON a.id = s.analisis_id WHERE a.id IS NULL"
        ).fetchone()[0]
        violaciones = conexion.execute("PRAGMA foreign_key_check").fetchall()
    finally:
        conexion.close()
    assert senales == 0
    assert fotogramas == 0
    assert huerfanas == 0
    assert violaciones == []


@pytest.mark.parametrize("gracia", [5.0, 0.0], ids=["cancelacion_del_proceso", "terminacion_forzada"])
def test_cancelacion_durante_la_ejecucion_con_worker_real(base, gracia):
    trabajo_id = _iniciar(base)
    nuevo = None
    worker = _worker(base, gracia)
    assert worker.iniciar()
    try:
        _esperar(lambda: _ejecutando_con_progreso(base, trabajo_id), 120, "El análisis no llegó a ejecutarse con progreso.")
        pid_hijo = _fila_trabajo(base, trabajo_id)["pid"]
        identidad_hijo = _fila_trabajo(base, trabajo_id)["identidad_proceso"]
        assert plataforma.identidad_proceso(pid_hijo) == identidad_hijo

        conexion = conectar(base["db"])
        try:
            trabajos.cancelar(conexion, trabajo_id)
        finally:
            conexion.close()

        _esperar(lambda: _fila_trabajo(base, trabajo_id)["estado"] == "cancelado", 60, "El trabajo no quedó cancelado.")
        _esperar(lambda: _estado_analisis(base) == "cancelado", 10, "El análisis no quedó cancelado.")
        _esperar(lambda: plataforma.identidad_proceso(pid_hijo) is None, 20, "El proceso hijo sigue vivo.")

        fila = _fila_trabajo(base, trabajo_id)
        assert fila["estado"] == "cancelado"
        assert fila["claim_token"] is None
        assert fila["pid"] is None
        assert fila["cancelacion_solicitada"] == 1
        assert worker.activo()
        _comprobar_sin_residuos(base)

        # El análisis cancelado se puede reintentar y el worker sigue aceptando trabajos.
        nuevo = _iniciar(base)
        assert nuevo != trabajo_id
        _esperar(lambda: _fila_trabajo(base, nuevo)["estado"] in ("en_cola", "ejecutando"), 30, "El reintento no se encoló.")
    finally:
        worker.detener()
    # Al detener el worker, el reintento vuelve a cola por parada ordenada, sin contar como fallo.
    assert _fila_trabajo(base, nuevo)["estado"] == "en_cola"
    assert _fila_trabajo(base, nuevo)["intentos"] == 0
    assert _estado_analisis(base) == "en_curso"
