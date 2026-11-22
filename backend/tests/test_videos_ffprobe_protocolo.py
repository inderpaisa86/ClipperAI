import json
import shutil
import subprocess
from pathlib import Path

import pytest

from app.modules.videos import ffprobe

requiere_ffprobe = pytest.mark.skipif(
    shutil.which("ffprobe") is None,
    reason="FFprobe debe estar disponible en PATH",
)

SALIDA_MINIMA = json.dumps(
    {
        "streams": [{"codec_type": "video", "codec_name": "h264", "width": 320, "height": 240}],
        "format": {"format_name": "mov,mp4", "duration": "2.0"},
    }
)


def _capturar_comando(monkeypatch, tmp_path: Path) -> list[str]:
    capturado: dict[str, list[str]] = {}
    ejecutable = tmp_path / "ffprobe-falso.exe"
    ejecutable.write_bytes(b"")

    def falso_run(comando, **_):
        capturado["comando"] = list(comando)
        return subprocess.CompletedProcess(comando, 0, stdout=SALIDA_MINIMA.encode("utf-8"), stderr=b"")

    monkeypatch.setattr(ffprobe.subprocess, "run", falso_run)
    video = tmp_path / "video.mp4"
    video.write_bytes(b"contenido")
    ffprobe.leer_metadatos(video, ejecutable, "windows", tamano_bytes=9)
    return capturado["comando"]


def test_ffprobe_restringe_el_protocolo_a_archivos_locales(monkeypatch, tmp_path):
    comando = _capturar_comando(monkeypatch, tmp_path)
    indice = comando.index("-protocol_whitelist")
    assert comando[indice + 1] == "file"
    assert indice < comando.index("-i")


def test_ffprobe_mantiene_argumentos_en_lista(monkeypatch, tmp_path):
    comando = _capturar_comando(monkeypatch, tmp_path)
    assert all(isinstance(argumento, str) for argumento in comando)
    assert comando[comando.index("-i") + 1].endswith("video.mp4")


@requiere_ffprobe
def test_ffprobe_con_protocolo_restringido_lee_un_archivo_local(generar_video):
    video = generar_video("local.mp4", segundos=1.0)
    ejecutable = shutil.which("ffprobe")
    metadatos = ffprobe.leer_metadatos(video, Path(ejecutable), "windows", tamano_bytes=video.stat().st_size)
    assert (metadatos.ancho, metadatos.alto) == (320, 240)
    assert metadatos.codec_video == "h264"
