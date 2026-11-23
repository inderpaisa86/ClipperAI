"""Política de eliminación de datos derivados: registros, miniaturas, enlaces y huérfanos."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.core.rutas import RaizDatos
from app.db.conexion import conectar
from app.jobs import service as trabajos
from app.modules.analisis import service as analisis
from app.modules.analisis.almacenamiento import AlmacenFotogramasVideo
from app.plugins.contrato import ResultadoSegmento, Senal
from tests.ayudas import (
    JPEG_PRUEBA,
    AnalizadorFalso,
    crear_proyecto,
    insertar_video_directo,
    persistir_en_transaccion,
    registro_con,
)

BASE = "/api/v1/videos"


def _video_con_miniaturas(cliente, configuracion, tiempos=(1000, 2000)) -> int:
    proyecto = crear_proyecto(cliente)
    conexion = conectar(configuracion.ruta_base_datos)
    try:
        video = insertar_video_directo(conexion, proyecto)
        raiz = RaizDatos(configuracion.data_dir)
        fila = analisis.preparar_analisis(conexion, video, "audio", registro_con(AnalizadorFalso("audio", "1")))
        almacen = AlmacenFotogramasVideo(raiz, video)
        fotogramas = tuple(almacen.guardar(t, JPEG_PRUEBA) for t in tiempos)
        persistir_en_transaccion(
            conexion,
            raiz,
            fila.id,
            ResultadoSegmento(
                senales=(Senal(tipo="energia_audio", inicio_ms=0, fin_ms=1000, valor=0.3, confianza=0.9),),
                fotogramas=fotogramas,
            ),
        )
        analisis.marcar_estado(conexion, fila.id, "completado")
        return video
    finally:
        conexion.close()


def _carpeta_fotogramas(configuracion, video_id: int) -> Path:
    return configuracion.data_dir / "work" / str(video_id) / "fotogramas"


def test_eliminar_borra_solo_las_miniaturas_del_video(cliente, configuracion):
    eliminado = _video_con_miniaturas(cliente, configuracion)
    otro = _video_con_miniaturas(cliente, configuracion, tiempos=(3000,))
    assert cliente.delete(f"{BASE}/{eliminado}").status_code == 204

    assert not _carpeta_fotogramas(configuracion, eliminado).exists()
    assert (_carpeta_fotogramas(configuracion, otro) / "3000.jpg").is_file()
    assert cliente.get(f"{BASE}/{otro}/analisis").status_code == 200


def test_eliminar_borra_los_temporales_del_video(cliente, configuracion):
    video = _video_con_miniaturas(cliente, configuracion)
    temporal = _carpeta_fotogramas(configuracion, video) / "9999.jpg.tmp"
    temporal.write_bytes(b"incompleto")
    assert cliente.delete(f"{BASE}/{video}").status_code == 204
    assert not _carpeta_fotogramas(configuracion, video).exists()


def test_eliminar_no_toca_el_original_del_video(cliente, configuracion, tmp_path):
    original = tmp_path / "medios" / "original.mp4"
    original.parent.mkdir()
    original.write_bytes(b"contenido original")
    proyecto = crear_proyecto(cliente)
    conexion = conectar(configuracion.ruta_base_datos)
    try:
        video = insertar_video_directo(conexion, proyecto)
        conexion.execute("UPDATE videos SET ruta_original = ? WHERE id = ?", (str(original), video))
        conexion.commit()
    finally:
        conexion.close()

    assert cliente.delete(f"{BASE}/{video}").status_code == 204
    assert original.read_bytes() == b"contenido original"


def test_eliminar_no_sigue_enlaces_hacia_fuera_de_data(cliente, configuracion, tmp_path):
    """Una carpeta de fotogramas convertida en enlace no debe llevar el borrado fuera de data/."""
    video = _video_con_miniaturas(cliente, configuracion)
    externo = tmp_path / "externo"
    externo.mkdir()
    precioso = externo / "1000.jpg"
    precioso.write_bytes(JPEG_PRUEBA)

    carpeta = _carpeta_fotogramas(configuracion, video)
    for archivo in carpeta.iterdir():
        archivo.unlink()
    carpeta.rmdir()
    if sys.platform == "win32":
        resultado = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(carpeta), str(externo)],
            capture_output=True,
            check=False,
        )
        if resultado.returncode != 0:
            pytest.skip("No se pudo crear un junction en este sistema.")
    else:
        os.symlink(externo, carpeta, target_is_directory=True)

    assert cliente.delete(f"{BASE}/{video}").status_code == 204
    assert precioso.read_bytes() == JPEG_PRUEBA


def test_fallo_al_borrar_deja_huerfano_y_el_arranque_lo_retira(cliente, configuracion, monkeypatch):
    video = _video_con_miniaturas(cliente, configuracion, tiempos=(1000,))
    archivo = _carpeta_fotogramas(configuracion, video) / "1000.jpg"
    original_unlink = Path.unlink

    def unlink_con_fallo(self, *args, **kwargs):
        if self.name == archivo.name and self.parent.name == "fotogramas":
            raise PermissionError("bloqueado")
        return original_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", unlink_con_fallo)
    # La eliminación responde 204 aunque una miniatura no se pueda borrar: el registro ya está confirmado.
    assert cliente.delete(f"{BASE}/{video}").status_code == 204
    assert archivo.is_file()

    monkeypatch.setattr(Path, "unlink", original_unlink)
    conexion = conectar(configuracion.ruta_base_datos)
    try:
        retirados = analisis.limpiar_derivados_huerfanos(conexion, RaizDatos(configuracion.data_dir))
    finally:
        conexion.close()
    assert retirados >= 1
    assert not archivo.exists()


def test_limpieza_de_arranque_no_toca_videos_existentes_ni_carpetas_ajenas(cliente, configuracion):
    vivo = _video_con_miniaturas(cliente, configuracion)
    ajena = configuracion.data_dir / "work" / "trabajos"
    ajena.mkdir(parents=True, exist_ok=True)
    (ajena / "nota.jpg").write_bytes(JPEG_PRUEBA)

    conexion = conectar(configuracion.ruta_base_datos)
    try:
        analisis.limpiar_derivados_huerfanos(conexion, RaizDatos(configuracion.data_dir))
    finally:
        conexion.close()

    assert (_carpeta_fotogramas(configuracion, vivo) / "1000.jpg").is_file()
    assert (ajena / "nota.jpg").is_file()


def test_eliminar_con_analisis_activo_responde_409_y_no_borra_nada(cliente, configuracion):
    video = _video_con_miniaturas(cliente, configuracion)
    conexion = conectar(configuracion.ruta_base_datos)
    try:
        # Un trabajo en cola que reserva el análisis del video, como haría el inicio de un análisis real.
        trabajos.crear(
            conexion,
            "diagnostico_espera",
            {"segundos": 0.1},
            al_insertar=lambda c, trabajo_id: analisis.reservar_para_trabajo(
                c, video, "audio", "1", trabajo_id
            ),
        )
    finally:
        conexion.close()

    respuesta = cliente.delete(f"{BASE}/{video}")
    assert respuesta.status_code == 409
    assert (_carpeta_fotogramas(configuracion, video) / "1000.jpg").is_file()
    assert cliente.get(f"{BASE}/{video}").status_code == 200


def test_eliminar_video_con_analisis_terminado_tras_interrupcion_si_se_permite(cliente, configuracion):
    """Un análisis en curso cuyo trabajo ya terminó no bloquea la eliminación."""
    video = _video_con_miniaturas(cliente, configuracion)
    conexion = conectar(configuracion.ruta_base_datos)
    try:
        trabajo = trabajos.crear(conexion, "diagnostico_espera", {"segundos": 0.1})
        trabajos.cancelar(conexion, trabajo)
        conexion.execute(
            "UPDATE analisis SET estado = 'en_curso', trabajo_id = ? WHERE video_id = ?", (trabajo, video)
        )
        conexion.commit()
    finally:
        conexion.close()

    assert cliente.delete(f"{BASE}/{video}").status_code == 204


def test_analisis_en_curso_cuyo_trabajo_cancelado_se_muestra_como_cancelado(cliente, configuracion):
    video = _video_con_miniaturas(cliente, configuracion)
    conexion = conectar(configuracion.ruta_base_datos)
    try:
        trabajo = trabajos.crear(conexion, "diagnostico_espera", {"segundos": 0.1})
        trabajos.cancelar(conexion, trabajo)
        conexion.execute(
            "UPDATE analisis SET estado = 'en_curso', trabajo_id = ? WHERE video_id = ?", (trabajo, video)
        )
        conexion.commit()
    finally:
        conexion.close()

    respuesta = cliente.get(f"{BASE}/{video}/analisis/audio").json()
    assert respuesta["estado"] == "cancelado"
    assert respuesta["error"] == "Análisis cancelado."
