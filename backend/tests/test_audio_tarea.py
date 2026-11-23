"""Tarea de audio: cancelación durante la ejecución y señales en el límite de 60 s entre segmentos."""

import shutil
import subprocess
from pathlib import Path

import pytest

from app.composicion import registrar
from app.db.conexion import conectar
from app.db.migraciones import aplicar_migraciones
from app.jobs import service as trabajos
from app.jobs.service import TrabajoCancelado
from app.modules.analisis import service as analisis
from app.modules.audio import analizador, service as audio, tarea
from app.modules.audio.energia import db_desde_valor
from app.modules.audio.senales import PuntoEnergia, consolidar
from app.modules.projects import service as proyectos
from app.modules.projects.schemas import ProyectoCrear
from app.modules.videos import repository as videos_repo
from app.plugins.contrato import SegmentoEntrada
from tests.conftest import requiere_ffmpeg


@pytest.fixture
def base(tmp_path):
    registrar()
    datos = tmp_path / "datos"
    ruta_db = datos / "clipperai.db"
    conexion = conectar(ruta_db)
    try:
        aplicar_migraciones(conexion)
        proyecto = proyectos.crear(conexion, ProyectoCrear(nombre="Tarea de audio")).id
    finally:
        conexion.close()
    return {"tmp": tmp_path, "datos": datos, "db": ruta_db, "proyecto": proyecto}


def _video(base, ruta: Path, duracion: float) -> int:
    conexion = conectar(base["db"])
    try:
        return videos_repo.insertar(
            conexion,
            {
                "proyecto_id": base["proyecto"],
                "nombre": ruta.name,
                "ruta_original": str(ruta),
                "tamano_bytes": ruta.stat().st_size,
                "duracion_segundos": duracion,
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


class _CtxCancelado:
    """Contexto mínimo de un trabajo que recibe una cancelación en su primer punto de control."""

    def __init__(self, ruta_db: Path, conexion, trabajo_id: int, token: str) -> None:
        self.ruta_db = ruta_db
        self.conexion = conexion
        self.trabajo_id = trabajo_id
        self.token = token
        self.llamadas = 0

    def verificar_cancelacion(self) -> None:
        self.llamadas += 1
        raise TrabajoCancelado()

    def progreso(self, valor: int) -> None:
        return None


def test_cancelacion_durante_la_ejecucion_marca_el_analisis_como_cancelado(base):
    ruta = base["tmp"] / "medio.mp4"
    ruta.write_bytes(b"no se decodifica: la cancelacion ocurre antes de leer el audio")
    video = _video(base, ruta, 3.0)

    conexion = conectar(base["db"])
    try:
        audio.iniciar_analisis(conexion, video)
        token = "t" * 32
        trabajo_id = trabajos.reclamar_siguiente(conexion, token)
        assert trabajo_id is not None
        ctx = _CtxCancelado(base["db"], conexion, trabajo_id, token)
        with pytest.raises(TrabajoCancelado):
            tarea.analisis_audio({"video_id": video, "analizador": "audio"}, ctx)
        assert ctx.llamadas == 1
        respuesta = analisis.obtener_analisis(conexion, video, "audio")
    finally:
        conexion.close()
    assert respuesta.estado == "cancelado"
    assert respuesta.error == "Análisis cancelado."


def test_cancelacion_en_cola_no_ejecuta_la_tarea_y_cierra_el_analisis(base):
    ruta = base["tmp"] / "en_cola.mp4"
    ruta.write_bytes(b"x")
    video = _video(base, ruta, 3.0)
    conexion = conectar(base["db"])
    try:
        trabajo_id = audio.iniciar_analisis(conexion, video)
        trabajos.cancelar(conexion, trabajo_id)
        respuesta = analisis.obtener_analisis(conexion, video, "audio")
        fila = conexion.execute(
            "SELECT estado FROM analisis WHERE video_id = ? AND analizador = 'audio'", (video,)
        ).fetchone()
    finally:
        conexion.close()
    assert fila["estado"] == "cancelado"
    assert respuesta.error == "Análisis cancelado."


@requiere_ffmpeg
def test_senales_en_el_limite_de_60_segundos_se_unen_sin_duplicar(tmp_path):
    """Un video de 61 s: tono hasta 60 s y silencio de 1 s. El límite del segmento cae en 60 000 ms."""
    destino = tmp_path / "61s.mp4"
    comando = [
        "ffmpeg", "-v", "error", "-y",
        "-f", "lavfi", "-i", "color=size=16x16:rate=1:duration=61",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=60",
        "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono:d=1",
        "-filter_complex",
        "[1:a]aresample=16000[a1];[2:a]aresample=16000[a2];[a1][a2]concat=n=2:v=0:a=1[a]",
        "-map", "0:v", "-map", "[a]",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
        str(destino),
    ]
    subprocess.run(comando, check=True, capture_output=True)
    ffmpeg = Path(shutil.which("ffmpeg"))
    adaptador = analizador.AnalizadorAudio(ffmpeg=ffmpeg)

    primero = adaptador.analizar_segmento(SegmentoEntrada(destino, 0, 60_000))
    segundo = adaptador.analizar_segmento(SegmentoEntrada(destino, 60_000, 61_000))

    inicios_segundo = [s.inicio_ms for s in segundo.senales]
    assert inicios_segundo[0] == 60_000
    assert inicios_segundo == list(range(60_000, 61_000, 200))
    assert len(primero.senales) == 300
    assert primero.senales[-1].fin_ms == 60_000

    # Las ventanas de los dos segmentos forman una serie continua: sin duplicados ni huecos en el límite.
    puntos = [
        PuntoEnergia(s.inicio_ms, s.fin_ms, db_desde_valor(s.valor))
        for s in primero.senales + segundo.senales
    ]
    assert len({p.inicio_ms for p in puntos}) == len(puntos) == 305
    silencios = [s for s in consolidar(puntos) if s.tipo == "silencio"]
    assert len(silencios) == 1
    assert abs(silencios[0].inicio_ms - 60_000) <= 200
    assert silencios[0].fin_ms == 61_000
