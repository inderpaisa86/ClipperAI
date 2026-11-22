import pytest

from app.core.rutas import RaizDatos, RutaNoPermitida


def test_resuelve_ruta_relativa_dentro_de_la_raiz(tmp_path):
    raiz = RaizDatos(tmp_path)

    resuelta = raiz.resolver("media/video.mp4")

    assert resuelta == (tmp_path / "media" / "video.mp4").resolve()


@pytest.mark.parametrize("ruta", ["../fuera.txt", "media/../../fuera.txt"])
def test_rechaza_subir_de_la_raiz(tmp_path, ruta):
    raiz = RaizDatos(tmp_path)

    with pytest.raises(RutaNoPermitida):
        raiz.resolver(ruta)


def test_rechaza_rutas_absolutas(tmp_path):
    raiz = RaizDatos(tmp_path)

    with pytest.raises(RutaNoPermitida):
        raiz.resolver(str(tmp_path / "video.mp4"))
