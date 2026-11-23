"""Ninguna respuesta pública de la API expone rutas absolutas del sistema."""

from pathlib import Path

from app.db.conexion import conectar
from app.modules.videos.schemas import SeleccionRespuesta, VideoRespuesta
from tests.ayudas import crear_proyecto, importar_video, insertar_video_directo
from tests.conftest import requiere_ffmpeg

RUTA_FALSA = "/medios/privado/original.mp4"


def _rutas_prohibidas(configuracion, *extra: Path | str) -> list[str]:
    base = [str(configuracion.data_dir), str(configuracion.data_dir.parent), RUTA_FALSA]
    base += [str(texto) for texto in extra]
    return [texto for texto in base if texto]


def _sin_rutas(respuesta, prohibidas: list[str]) -> None:
    cuerpo = respuesta.text
    for ruta in prohibidas:
        assert ruta not in cuerpo, f"La respuesta {respuesta.request.method} {respuesta.request.url.path} expone {ruta}"


def test_el_contrato_de_video_no_declara_ruta():
    assert "ruta" not in VideoRespuesta.model_fields
    assert "ruta_original" not in VideoRespuesta.model_fields
    assert "nombre_archivo" in VideoRespuesta.model_fields
    assert set(SeleccionRespuesta.model_fields) == {"seleccion_id", "nombre_archivo"}


def test_respuestas_de_videos_y_analisis_sin_rutas_privadas(cliente, configuracion):
    proyecto = crear_proyecto(cliente)
    conexion = conectar(configuracion.ruta_base_datos)
    try:
        video = insertar_video_directo(conexion, proyecto, nombre="partida.mp4")
        conexion.execute("UPDATE videos SET ruta_original = ? WHERE id = ?", (RUTA_FALSA, video))
        conexion.commit()
    finally:
        conexion.close()
    prohibidas = _rutas_prohibidas(configuracion)

    listado = cliente.get(f"/api/v1/videos?proyecto_id={proyecto}")
    assert listado.status_code == 200
    _sin_rutas(listado, prohibidas)
    assert listado.json()[0]["nombre_archivo"] == "original.mp4"

    _sin_rutas(cliente.get(f"/api/v1/videos/{video}"), prohibidas)
    _sin_rutas(cliente.get(f"/api/v1/videos/{video}/analisis"), prohibidas)
    _sin_rutas(cliente.get(f"/api/v1/videos/{video}/analisis/audio"), prohibidas)
    _sin_rutas(cliente.get(f"/api/v1/videos/{video}/analisis/audio/senales"), prohibidas)
    _sin_rutas(cliente.get(f"/api/v1/videos/{video}/analisis/audio/fotogramas"), prohibidas)
    _sin_rutas(cliente.get("/api/v1/proyectos"), prohibidas)


def test_errores_no_repiten_la_ruta_del_original(cliente, configuracion):
    respuesta = cliente.get("/api/v1/videos/987654")
    assert respuesta.status_code == 404
    _sin_rutas(respuesta, _rutas_prohibidas(configuracion))


def test_seleccion_cancelada_y_elegida_no_exponen_la_ruta(cliente, monkeypatch, tmp_path):
    elegida = tmp_path / "privado" / "elegido.mp4"
    prohibidas = _rutas_prohibidas(cliente.app.state.configuracion, elegida, elegida.parent)
    monkeypatch.setattr("app.modules.videos.router.seleccionar_video", lambda sistema: elegida)
    _sin_rutas(cliente.post("/api/v1/videos/seleccion"), prohibidas)


@requiere_ffmpeg
def test_importacion_real_no_devuelve_la_ruta_escrita(cliente, generar_video, configuracion):
    proyecto = crear_proyecto(cliente)
    ruta = generar_video("privado.mp4", audio=True)
    respuesta = importar_video(cliente, proyecto, ruta)
    assert respuesta.status_code == 201
    _sin_rutas(respuesta, _rutas_prohibidas(configuracion, ruta, ruta.parent))
    _sin_rutas(cliente.get(f"/api/v1/videos?proyecto_id={proyecto}"), _rutas_prohibidas(configuracion, ruta))

