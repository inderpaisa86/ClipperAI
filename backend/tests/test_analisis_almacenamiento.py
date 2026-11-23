import os
import subprocess
from pathlib import Path

import pytest

from app.core.errores import NoEncontrado
from app.core.rutas import RaizDatos, RutaNoPermitida
from app.modules.analisis.almacenamiento import (
    TAMANO_MAXIMO_MINIATURA_BYTES,
    AlmacenFotogramasVideo,
    barrer_huerfanos,
    ruta_relativa_fotograma,
    verificar_fotograma,
)
from app.plugins.contrato import ContratoInvalido

JPEG = b"\xff\xd8\xff\xe0" + b"0" * 128


@pytest.fixture
def raiz(tmp_path: Path) -> RaizDatos:
    datos = tmp_path / "datos"
    datos.mkdir()
    return RaizDatos(datos)


def _enlace_a_directorio(enlace: Path, destino: Path) -> bool:
    """Crea un enlace a directorio. En Windows usa junction, que no requiere privilegios."""
    destino.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        resultado = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(enlace), str(destino)], capture_output=True, check=False
        )
        return resultado.returncode == 0
    try:
        os.symlink(destino, enlace, target_is_directory=True)
    except OSError:
        return False
    return True


def test_ruta_relativa_sigue_el_formato_del_almacen():
    assert ruta_relativa_fotograma(7, 1500) == "work/7/fotogramas/1500.jpg"


@pytest.mark.parametrize("video_id, tiempo", [(0, 1), (-1, 1), (True, 1), (1, -1), (1, 1.5)])
def test_ruta_relativa_rechaza_identificadores_no_validos(video_id, tiempo):
    with pytest.raises(ContratoInvalido):
        ruta_relativa_fotograma(video_id, tiempo)


def test_guardar_escribe_el_jpeg_sin_dejar_temporales(raiz):
    registro = AlmacenFotogramasVideo(raiz, 7).guardar(1500, JPEG)
    destino = raiz.raiz / "work" / "7" / "fotogramas" / "1500.jpg"
    assert destino.read_bytes() == JPEG
    assert registro.ruta_relativa == "work/7/fotogramas/1500.jpg"
    assert list(destino.parent.glob("*.tmp")) == []


def test_guardar_de_nuevo_el_mismo_tiempo_sobrescribe(raiz):
    almacen = AlmacenFotogramasVideo(raiz, 7)
    almacen.guardar(1500, JPEG)
    nuevo = b"\xff\xd8\xff" + b"1" * 16
    almacen.guardar(1500, nuevo)
    assert (raiz.raiz / "work" / "7" / "fotogramas" / "1500.jpg").read_bytes() == nuevo


@pytest.mark.parametrize(
    "imagen",
    [b"\x89PNG\r\n\x1a\n" + b"0" * 32, b"", "texto", b"\xff\xd8"],
)
def test_guardar_rechaza_datos_que_no_son_jpeg(raiz, imagen):
    with pytest.raises(ContratoInvalido):
        AlmacenFotogramasVideo(raiz, 7).guardar(0, imagen)


def test_guardar_rechaza_imagen_demasiado_grande(raiz):
    grande = b"\xff\xd8\xff" + b"0" * TAMANO_MAXIMO_MINIATURA_BYTES
    with pytest.raises(ContratoInvalido):
        AlmacenFotogramasVideo(raiz, 7).guardar(0, grande)
    assert not (raiz.raiz / "work").exists()


def test_verificar_fotograma_inexistente_no_revela_la_ruta(raiz):
    with pytest.raises(NoEncontrado) as error:
        verificar_fotograma(raiz, "work/7/fotogramas/9.jpg")
    assert str(raiz.raiz) not in str(error.value)


@pytest.mark.parametrize("ruta", ["../clipperai.db", "/etc/passwd", "work/../../x.jpg"])
def test_verificar_fotograma_rechaza_rutas_que_salen_de_la_raiz(raiz, ruta):
    with pytest.raises(NoEncontrado):
        verificar_fotograma(raiz, ruta)


def test_guardar_no_sigue_un_directorio_enlazado_fuera_de_la_raiz(tmp_path, raiz):
    externo = tmp_path / "externo"
    if not _enlace_a_directorio(raiz.raiz / "work", externo):
        pytest.skip("No se pudo crear un enlace de directorio sin privilegios.")
    with pytest.raises(RutaNoPermitida):
        AlmacenFotogramasVideo(raiz, 7).guardar(0, JPEG)
    assert list(externo.iterdir()) == []


def test_verificar_fotograma_rechaza_un_video_enlazado_fuera_de_la_raiz(tmp_path, raiz):
    externo = tmp_path / "externo" / "fotogramas"
    externo.mkdir(parents=True)
    (externo / "0.jpg").write_bytes(JPEG)
    (raiz.raiz / "work").mkdir()
    if not _enlace_a_directorio(raiz.raiz / "work" / "7", externo.parent):
        pytest.skip("No se pudo crear un enlace de directorio sin privilegios.")
    with pytest.raises(NoEncontrado):
        verificar_fotograma(raiz, "work/7/fotogramas/0.jpg")


def test_barrido_borra_huerfanos_y_temporales_y_conserva_los_registrados(raiz):
    almacen = AlmacenFotogramasVideo(raiz, 7)
    almacen.guardar(1000, JPEG)
    almacen.guardar(2000, JPEG)
    carpeta = raiz.raiz / "work" / "7" / "fotogramas"
    (carpeta / "3000.jpg.tmp").write_bytes(JPEG)
    (carpeta / "subcarpeta").mkdir()

    eliminados = barrer_huerfanos(raiz, 7, {"work/7/fotogramas/1000.jpg"})

    assert eliminados == 2
    assert sorted(p.name for p in carpeta.iterdir()) == ["1000.jpg", "subcarpeta"]


def test_barrido_sin_directorio_no_hace_nada(raiz):
    assert barrer_huerfanos(raiz, 99, set()) == 0
