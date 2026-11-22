import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.configuracion import Configuracion
from app.main import ENCABEZADO_TOKEN, crear_aplicacion

requiere_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="FFmpeg y FFprobe deben estar disponibles en PATH",
)


@pytest.fixture
def configuracion(tmp_path: Path) -> Configuracion:
    # El worker se desactiva en el cliente de pruebas. Las pruebas de trabajos lo arrancan a mano.
    return Configuracion(data_dir=tmp_path / "datos", iniciar_trabajos=False)


@pytest.fixture
def cliente(configuracion: Configuracion):
    """Cliente HTTP con Host válido y token de sesión ya configurado."""
    aplicacion = crear_aplicacion(configuracion)
    with TestClient(aplicacion, base_url="http://127.0.0.1:8000") as http:
        http.headers[ENCABEZADO_TOKEN] = aplicacion.state.token
        yield http


@pytest.fixture
def generar_video(tmp_path: Path) -> Callable[..., Path]:
    """Crea un video real de prueba con FFmpeg. Requiere FFmpeg en PATH."""

    def _generar(nombre: str, *, audio: bool = False, segundos: float = 2.0) -> Path:
        destino = tmp_path / "medios" / nombre
        destino.parent.mkdir(parents=True, exist_ok=True)
        comando = [
            "ffmpeg", "-v", "error", "-y",
            "-f", "lavfi", "-i", f"testsrc=size=320x240:rate=25:duration={segundos}",
        ]
        if audio:
            comando += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={segundos}"]
            comando += ["-c:a", "aac"]
        comando += ["-c:v", "libx264", "-pix_fmt", "yuv420p", str(destino)]
        subprocess.run(comando, check=True, capture_output=True)
        return destino

    return _generar

