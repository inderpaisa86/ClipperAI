import shutil
from pathlib import Path

import pytest

from app.core.herramientas import (
    HerramientaNoDisponible,
    instruccion_instalacion,
    resolver_herramienta,
)
from app.core.plataforma import InfoPlataforma, detectar_plataforma


def test_detecta_sistema_y_arquitectura_conocidos():
    info = detectar_plataforma()

    assert info.sistema in {"windows", "macos", "linux", "desconocido"}
    assert info.arquitectura
    assert info.cpus_logicas >= 1


def test_identifica_apple_silicon_solo_en_macos_arm64():
    assert InfoPlataforma("macos", "arm64", 8).es_apple_silicon
    assert not InfoPlataforma("macos", "x86_64", 8).es_apple_silicon
    assert not InfoPlataforma("windows", "arm64", 8).es_apple_silicon


def test_instruccion_depende_del_sistema():
    assert "winget" in instruccion_instalacion("windows")
    assert "brew" in instruccion_instalacion("macos")
    assert "CLIPPERAI_FFMPEG" in instruccion_instalacion("linux")


def test_ruta_configurada_inexistente_falla_sin_buscar_en_path(tmp_path):
    inexistente = tmp_path / "ffmpeg-no-existe"

    with pytest.raises(HerramientaNoDisponible, match="no existe"):
        resolver_herramienta("ffmpeg", inexistente, "windows")


def test_sin_ruta_configurada_y_sin_path_muestra_instruccion(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda nombre: None)

    with pytest.raises(HerramientaNoDisponible, match="winget install Gyan.FFmpeg"):
        resolver_herramienta("ffmpeg", None, "windows")


def test_ruta_configurada_existente_se_usa_tal_cual(tmp_path):
    ejecutable = tmp_path / "ffmpeg.exe"
    ejecutable.write_bytes(b"")

    assert resolver_herramienta("ffmpeg", ejecutable, "windows") == Path(ejecutable)
