import os
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.ayudas import crear_proyecto, importar_video
from tests.conftest import requiere_ffmpeg


def _crear_enlace_directorio(enlace: Path, destino: Path) -> None:
    """Crea un junction (Windows) o un enlace simbólico (POSIX) a un directorio.

    Ambos casos pueden no estar disponibles según permisos. En ese caso la prueba se omite.
    """
    if os.name == "nt":
        resultado = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(enlace), str(destino)],
            capture_output=True,
            text=True,
            check=False,
        )
        if resultado.returncode != 0:
            pytest.skip(f"No se pudo crear el junction: {resultado.stdout} {resultado.stderr}")
        return
    try:
        os.symlink(destino, enlace, target_is_directory=True)
    except OSError:
        pytest.skip("El sistema no permite crear enlaces a directorios")


@requiere_ffmpeg
def test_rechaza_ruta_cuyo_directorio_padre_es_enlace(cliente, generar_video, tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    shutil.copy(generar_video("video.mp4"), real / "video.mp4")
    acceso = tmp_path / "acceso"
    _crear_enlace_directorio(acceso, real)
    proyecto_id = crear_proyecto(cliente)

    respuesta = importar_video(cliente, proyecto_id, acceso / "video.mp4")

    assert respuesta.status_code == 422
    assert "enlaces simbólicos" in respuesta.json()["detalle"]


@requiere_ffmpeg
def test_rechaza_ruta_con_componente_parent_antes_del_archivo(cliente, generar_video, tmp_path):
    shutil.copy(generar_video("video.mp4"), tmp_path / "video.mp4")
    (tmp_path / "carpeta").mkdir()
    proyecto_id = crear_proyecto(cliente)

    respuesta = importar_video(cliente, proyecto_id, tmp_path / "carpeta" / ".." / "video.mp4")

    assert respuesta.status_code == 422
    assert respuesta.json()["detalle"] == "La ruta no puede contener '..'."


@requiere_ffmpeg
def test_transmision_no_sigue_un_enlace_creado_despues_de_importar(
    cliente, generar_video, tmp_path
):
    """Si el directorio original se reemplaza por un enlace a otro, el video deja de estar disponible."""
    carpeta = tmp_path / "originales"
    carpeta.mkdir()
    shutil.copy(generar_video("video.mp4"), carpeta / "video.mp4")
    proyecto_id = crear_proyecto(cliente)
    video = importar_video(cliente, proyecto_id, carpeta / "video.mp4").json()

    otra = tmp_path / "otra"
    otra.mkdir()
    shutil.copy(generar_video("otro.mp4", segundos=1), otra / "video.mp4")
    contenido_suplantado = (otra / "video.mp4").read_bytes()
    shutil.move(carpeta, tmp_path / "originales_movidos")
    _crear_enlace_directorio(carpeta, otra)

    transmision = cliente.get(f"/api/v1/videos/{video['id']}/stream")
    listado = cliente.get(f"/api/v1/videos?proyecto_id={proyecto_id}").json()

    assert transmision.status_code == 404
    assert contenido_suplantado not in transmision.content
    assert listado[0]["disponible"] is False


@requiere_ffmpeg
def test_video_sigue_disponible_con_ruta_normal(cliente, generar_video, tmp_path):
    """Control negativo: sin enlaces, la transmisión y la disponibilidad funcionan."""
    carpeta = tmp_path / "normal"
    carpeta.mkdir()
    shutil.copy(generar_video("normal.mp4"), carpeta / "normal.mp4")
    proyecto_id = crear_proyecto(cliente)
    video = importar_video(cliente, proyecto_id, carpeta / "normal.mp4").json()

    transmision = cliente.get(f"/api/v1/videos/{video['id']}/stream")
    listado = cliente.get(f"/api/v1/videos?proyecto_id={proyecto_id}").json()

    assert transmision.status_code == 200
    assert listado[0]["disponible"] is True
