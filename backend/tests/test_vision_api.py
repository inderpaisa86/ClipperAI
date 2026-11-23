"""Inicio y consulta del análisis visual por la API existente. Requiere FFmpeg y FFprobe."""
from tests.conftest import requiere_ffmpeg
from tests.ayudas import crear_proyecto, importar_video

pytestmark = requiere_ffmpeg


def _importar(cliente, tmp_path, generar_video):
    proyecto = crear_proyecto(cliente)
    video = generar_video("visual.mp4", segundos=2.0)
    respuesta = importar_video(cliente, proyecto, video)
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()["id"], video


def test_post_analisis_inicia_el_analizador_visual_junto_al_de_audio(cliente, tmp_path, generar_video):
    video_id, _ = _importar(cliente, tmp_path, generar_video)
    respuesta = cliente.post(f"/api/v1/videos/{video_id}/analisis")
    assert respuesta.status_code == 202, respuesta.text
    items = {item["analizador"]: item for item in respuesta.json()}
    assert items["video"]["accion"] == "iniciado"
    assert items["video"]["trabajo_id"] is not None
    assert items["audio"]["accion"] == "rechazado"


def test_consulta_del_analisis_visual_devuelve_el_estado_sin_rutas(cliente, tmp_path, generar_video):
    video_id, original = _importar(cliente, tmp_path, generar_video)
    cliente.post(f"/api/v1/videos/{video_id}/analisis")
    respuesta = cliente.get(f"/api/v1/videos/{video_id}/analisis/video")
    assert respuesta.status_code == 200
    assert respuesta.json()["estado"] == "en_curso"
    for ruta in (
        cliente.get(f"/api/v1/videos/{video_id}/analisis").text,
        respuesta.text,
    ):
        assert str(original.parent) not in ruta


def test_senales_aceptan_los_tipos_visuales_y_rechazan_los_desconocidos(cliente, tmp_path, generar_video):
    video_id, _ = _importar(cliente, tmp_path, generar_video)
    cliente.post(f"/api/v1/videos/{video_id}/analisis")
    for tipo in ("brillo", "movimiento", "cambio_escena"):
        respuesta = cliente.get(f"/api/v1/videos/{video_id}/analisis/video/senales?tipo={tipo}")
        assert respuesta.status_code == 200, respuesta.text
        assert respuesta.json() == []
    respuesta = cliente.get(f"/api/v1/videos/{video_id}/analisis/video/senales?tipo=escena")
    assert respuesta.status_code == 422


def test_fotogramas_del_analisis_visual_no_exponen_rutas(cliente, tmp_path, generar_video):
    video_id, original = _importar(cliente, tmp_path, generar_video)
    cliente.post(f"/api/v1/videos/{video_id}/analisis")
    respuesta = cliente.get(f"/api/v1/videos/{video_id}/analisis/video/fotogramas")
    assert respuesta.status_code == 200
    assert str(original.parent) not in respuesta.text
    assert "ruta" not in respuesta.text
