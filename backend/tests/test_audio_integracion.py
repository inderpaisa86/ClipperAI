"""Analizador de audio con FFmpeg real y con el sistema de trabajos. Requiere FFmpeg y FFprobe."""

import shutil
import subprocess
import time
from pathlib import Path

import pytest

from app.composicion import registrar
from app.core.errores import Conflicto, SolicitudInvalida
from app.core.rutas import RaizDatos
from app.db.conexion import conectar
from app.db.migraciones import aplicar_migraciones
from app.jobs import service as trabajos
from app.jobs import tareas
from app.jobs.worker import Worker
from app.modules.analisis import service as analisis
from app.modules.audio import analizador
from app.modules.audio import service as audio
from app.modules.audio.energia import ErrorAudio, ventanas_de_rango
from app.modules.projects import service as proyectos
from app.modules.projects.schemas import ProyectoCrear
from app.modules.videos import repository as videos_repo
from app.plugins.contrato import SegmentoEntrada
from app.plugins.registro import REGISTRO
from tests.conftest import requiere_ffmpeg

pytestmark = requiere_ffmpeg


@pytest.fixture(autouse=True)
def _registro_listo():
    registrar()
    yield


def _ffmpeg() -> Path:
    ruta = shutil.which("ffmpeg")
    assert ruta is not None
    return Path(ruta)


def _video_silencio_central(destino: Path) -> Path:
    """Video de 3 s: 1 s de tono, 1 s de silencio digital y 1 s de tono. Con audio AAC."""
    comando = [
        "ffmpeg", "-v", "error", "-y",
        "-f", "lavfi", "-i", "testsrc=size=160x120:rate=10:duration=3",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
        "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono:d=1",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
        "-filter_complex",
        "[1:a]aresample=16000[a1];[2:a]aresample=16000[a2];[3:a]aresample=16000[a3];"
        "[a1][a2][a3]concat=n=3:v=0:a=1[a]",
        "-map", "0:v", "-map", "[a]",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
        str(destino),
    ]
    subprocess.run(comando, check=True, capture_output=True)
    return destino


def _video_sin_audio(destino: Path) -> Path:
    comando = [
        "ffmpeg", "-v", "error", "-y",
        "-f", "lavfi", "-i", "testsrc=size=160x120:rate=10:duration=2",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an",
        str(destino),
    ]
    subprocess.run(comando, check=True, capture_output=True)
    return destino


@pytest.fixture
def base(tmp_path):
    datos = tmp_path / "datos"
    ruta_db = datos / "clipperai.db"
    conexion = conectar(ruta_db)
    try:
        aplicar_migraciones(conexion)
        proyecto = proyectos.crear(conexion, ProyectoCrear(nombre="Prueba de audio")).id
    finally:
        conexion.close()
    return {"datos": datos, "db": ruta_db, "lock": datos / "runtime" / "worker.lock", "proyecto": proyecto}


def _registrar_video(base, ruta: Path, *, duracion: float | None, audio: bool) -> int:
    conexion = conectar(base["db"])
    try:
        video = videos_repo.insertar(
            conexion,
            {
                "proyecto_id": base["proyecto"],
                "nombre": ruta.name,
                "ruta_original": str(ruta),
                "tamano_bytes": ruta.stat().st_size,
                "duracion_segundos": duracion,
                "ancho": 160,
                "alto": 120,
                "fps": 10.0,
                "codec_video": "h264",
                "codec_audio": "aac" if audio else None,
                "formato": "mp4",
            },
        )
    finally:
        conexion.close()
    return video


def _esperar(condicion, segundos: float, mensaje: str):
    limite = time.monotonic() + segundos
    while time.monotonic() < limite:
        if condicion():
            return
        time.sleep(0.2)
    raise AssertionError(mensaje)


def _estado_analisis(base, video_id: int) -> str:
    conexion = conectar(base["db"])
    try:
        return analisis.obtener_analisis(conexion, video_id, "audio").estado
    finally:
        conexion.close()


def _trabajo_worker(base) -> Worker:
    worker = Worker(
        base["db"],
        base["lock"],
        RaizDatos(base["datos"]),
        intervalo_sondeo=0.1,
        intervalo_latido=0.3,
        gracia_cancelacion=5.0,
        intervalo_recuperacion=0.5,
    )
    return worker


# -- Análisis directo del segmento -------------------------------------------------


def test_analizar_segmento_produce_una_senal_de_energia_por_ventana(tmp_path):
    video = _video_silencio_central(tmp_path / "medio.mp4")
    adaptador = analizador.AnalizadorAudio(ffmpeg=_ffmpeg())

    resultado = adaptador.analizar_segmento(SegmentoEntrada(video, 0, 3000))
    senales = resultado.senales
    assert len(senales) == 15
    assert all(s.tipo == "energia_audio" for s in senales)
    assert all(s.fin_ms - s.inicio_ms == 200 for s in senales)
    inicios = [s.inicio_ms for s in senales]
    assert inicios == list(range(0, 3000, 200))
    tonos = [s.valor for s in senales[:5]]
    # La primera ventana de silencio aún contiene la cola de codificación AAC del tono (unos -80 dB).
    # Por eso el silencio completo se mide desde la sexta ventana.
    silencio = [s.valor for s in senales[6:10]]
    assert min(tonos) > 0.5
    assert max(silencio) < 0.1


def test_segmento_intermedio_respeta_el_desplazamiento_en_milisegundos(tmp_path):
    video = _video_silencio_central(tmp_path / "medio.mp4")
    senales = list(
        ventanas_de_rango(_ffmpeg(), video, 1000, 2000, lambda: None)
    )
    assert len(senales) == 5
    assert senales[0].inicio_ms == 1000
    assert all(v.rms < 0.001 for v in senales)


def test_cancelacion_durante_la_lectura_detiene_el_analisis(tmp_path):
    class Cancelado(Exception):
        pass

    video = _video_silencio_central(tmp_path / "medio.mp4")
    contador = {"n": 0}

    def verificar():
        contador["n"] += 1
        if contador["n"] == 4:
            raise Cancelado()

    with pytest.raises(Cancelado):
        list(ventanas_de_rango(_ffmpeg(), video, 0, 3000, verificar))


def test_error_de_ffmpeg_no_expone_la_ruta(tmp_path):
    texto = tmp_path / "no_es_video.mp4"
    texto.write_text("contenido que no es audio", encoding="utf-8")
    with pytest.raises(ErrorAudio) as error:
        list(ventanas_de_rango(_ffmpeg(), texto, 0, 1000, lambda: None))
    assert str(tmp_path) not in str(error.value)


# -- Ciclo completo con el sistema de trabajos ---------------------------------------


def test_analisis_completo_por_el_worker_persiste_senales_y_silencios(base):
    video_ruta = _video_silencio_central(base["datos"].parent / "medios_prueba.mp4")
    video = _registrar_video(base, video_ruta, duracion=3.0, audio=True)

    conexion = conectar(base["db"])
    try:
        trabajo = audio.iniciar_analisis(conexion, video)
    finally:
        conexion.close()

    worker = _trabajo_worker(base)
    assert worker.iniciar()
    try:
        _esperar(lambda: _estado_analisis(base, video) in ("completado", "fallido"), 120, "El análisis no terminó.")
    finally:
        worker.detener()

    assert _estado_analisis(base, video) == "completado"
    conexion = conectar(base["db"])
    try:
        assert trabajos.consultar(conexion, trabajo)["estado"] == "completado"
        senales = analisis.listar_senales(conexion, video, "audio", None, None, 2000)
        version = analisis.obtener_analisis(conexion, video, "audio").version_analizador
        fotogramas = analisis.listar_fotogramas(conexion, video, "audio")
    finally:
        conexion.close()

    assert version == analizador.VERSION
    assert fotogramas == []
    tipos = {senal.tipo for senal in senales}
    assert tipos == {"energia_audio", "silencio", "cambio_intensidad"}
    energia = [s for s in senales if s.tipo == "energia_audio"]
    assert len(energia) == 15

    silencios = [s for s in senales if s.tipo == "silencio"]
    assert len(silencios) == 1
    assert abs(silencios[0].inicio_ms - 1000) <= 200
    assert abs(silencios[0].fin_ms - 2000) <= 200

    cambios = [s.inicio_ms for s in senales if s.tipo == "cambio_intensidad"]
    assert any(abs(inicio - 800) <= 200 for inicio in cambios)
    assert any(abs(inicio - 1800) <= 200 for inicio in cambios)

    conexion = conectar(base["db"])
    try:
        with pytest.raises(Conflicto):
            audio.iniciar_analisis(conexion, video)
    finally:
        conexion.close()


def test_video_con_error_de_lectura_deja_el_analisis_fallido(base):
    texto = base["datos"].parent / "no_es_video.mp4"
    texto.parent.mkdir(parents=True, exist_ok=True)
    texto.write_text("no es un video", encoding="utf-8")
    video = _registrar_video(base, texto, duracion=3.0, audio=True)

    conexion = conectar(base["db"])
    try:
        trabajo = audio.iniciar_analisis(conexion, video)
    finally:
        conexion.close()

    worker = _trabajo_worker(base)
    assert worker.iniciar()
    try:
        _esperar(lambda: _estado_analisis(base, video) == "fallido", 120, "El análisis no falló.")
    finally:
        worker.detener()

    conexion = conectar(base["db"])
    try:
        assert trabajos.consultar(conexion, trabajo)["estado"] == "fallido"
        error = analisis.obtener_analisis(conexion, video, "audio").error
    finally:
        conexion.close()
    assert error == "FFmpeg no pudo leer el audio del segmento."
    assert str(texto) not in error


def test_cancelar_en_cola_deja_el_analisis_cancelado_y_permite_reintentar(base):
    video_ruta = _video_silencio_central(base["datos"].parent / "cancelable.mp4")
    video = _registrar_video(base, video_ruta, duracion=3.0, audio=True)

    conexion = conectar(base["db"])
    try:
        trabajo = audio.iniciar_analisis(conexion, video)
        trabajos.cancelar(conexion, trabajo)
    finally:
        conexion.close()

    assert _estado_analisis(base, video) == "cancelado"

    conexion = conectar(base["db"])
    try:
        nuevo = audio.iniciar_analisis(conexion, video)
    finally:
        conexion.close()
    assert nuevo != trabajo


def test_video_sin_pista_de_audio_no_se_analiza(base):
    sin_audio = _video_sin_audio(base["datos"].parent / "mudo.mp4")
    video = _registrar_video(base, sin_audio, duracion=2.0, audio=False)
    conexion = conectar(base["db"])
    try:
        with pytest.raises(SolicitudInvalida, match="pista de audio"):
            audio.iniciar_analisis(conexion, video)
    finally:
        conexion.close()


def test_video_sin_duracion_conocida_no_se_analiza(base):
    video_ruta = _video_silencio_central(base["datos"].parent / "sin_duracion.mp4")
    video = _registrar_video(base, video_ruta, duracion=None, audio=True)
    conexion = conectar(base["db"])
    try:
        with pytest.raises(SolicitudInvalida, match="duración"):
            audio.iniciar_analisis(conexion, video)
    finally:
        conexion.close()


def test_tipo_de_trabajo_y_analizador_quedan_registrados():
    assert "analisis_audio" in tareas.REGISTRO
    assert REGISTRO.existe("audio")
