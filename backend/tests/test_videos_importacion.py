import os
import shutil

import pytest

from app.core.errores import SolicitudInvalida
from app.modules.videos.ffprobe import interpretar_metadatos
from app.modules.videos.service import validar_ruta_entrada
from tests.ayudas import crear_proyecto, importar_video
from tests.conftest import requiere_ffmpeg


@requiere_ffmpeg
def test_importa_mp4_valido_con_metadatos(cliente, generar_video):
    proyecto_id = crear_proyecto(cliente)
    ruta = generar_video("partida.mp4", audio=True, segundos=2)

    respuesta = importar_video(cliente, proyecto_id, ruta)

    assert respuesta.status_code == 201, respuesta.text
    video = respuesta.json()
    assert video["nombre"] == "partida.mp4"
    assert video["nombre_archivo"] == "partida.mp4"
    assert "ruta" not in video
    assert str(ruta) not in respuesta.text
    assert video["ancho"] == 320
    assert video["alto"] == 240
    assert video["fps"] == pytest.approx(25.0, abs=0.01)
    assert video["codec_video"] == "h264"
    assert video["codec_audio"] == "aac"
    assert video["duracion_segundos"] == pytest.approx(2.0, abs=0.3)
    assert video["tamano_bytes"] == ruta.stat().st_size
    assert video["formato"]
    assert video["disponible"] is True


@requiere_ffmpeg
def test_importa_mkv_sin_audio(cliente, generar_video):
    proyecto_id = crear_proyecto(cliente)
    ruta = generar_video("charla.mkv", audio=False)

    respuesta = importar_video(cliente, proyecto_id, ruta)

    assert respuesta.status_code == 201, respuesta.text
    assert respuesta.json()["codec_audio"] is None


def test_rechaza_archivo_inexistente(cliente, tmp_path):
    proyecto_id = crear_proyecto(cliente)

    respuesta = importar_video(cliente, proyecto_id, tmp_path / "no_existe.mp4")

    assert respuesta.status_code == 422
    assert respuesta.json()["detalle"] == "El archivo no existe."


def test_rechaza_extension_no_compatible(cliente, tmp_path):
    proyecto_id = crear_proyecto(cliente)
    documento = tmp_path / "notas.txt"
    documento.write_text("no es un video", encoding="utf-8")

    respuesta = importar_video(cliente, proyecto_id, documento)

    assert respuesta.status_code == 422
    assert respuesta.json()["detalle"].startswith("Formato no compatible")


def test_rechaza_contenedor_corrupto_con_extension_valida(cliente, tmp_path):
    proyecto_id = crear_proyecto(cliente)
    falso = tmp_path / "corrupto.mp4"
    falso.write_bytes(b"esto no es un contenedor de video" * 100)

    respuesta = importar_video(cliente, proyecto_id, falso)

    assert respuesta.status_code == 422
    assert respuesta.json()["detalle"].startswith("FFprobe no pudo leer el archivo")


def test_rechaza_archivo_vacio(cliente, tmp_path):
    proyecto_id = crear_proyecto(cliente)
    vacio = tmp_path / "vacio.mp4"
    vacio.touch()

    respuesta = importar_video(cliente, proyecto_id, vacio)

    assert respuesta.status_code == 422
    assert respuesta.json()["detalle"] == "El archivo está vacío."


def test_rechaza_ruta_relativa(cliente):
    proyecto_id = crear_proyecto(cliente)

    respuesta = cliente.post(
        "/api/v1/videos", json={"proyecto_id": proyecto_id, "ruta": "videos/partida.mp4"}
    )

    assert respuesta.status_code == 422
    assert respuesta.json()["detalle"] == "La ruta debe ser absoluta."


def test_rechaza_ruta_con_byte_nulo(cliente, tmp_path):
    proyecto_id = crear_proyecto(cliente)

    respuesta = importar_video(cliente, proyecto_id, str(tmp_path / "a\x00b.mp4"))

    assert respuesta.status_code == 422


def test_rechaza_directorio_con_extension_valida(cliente, tmp_path):
    proyecto_id = crear_proyecto(cliente)
    carpeta = tmp_path / "carpeta.mp4"
    carpeta.mkdir()

    respuesta = importar_video(cliente, proyecto_id, carpeta)

    assert respuesta.status_code == 422
    assert respuesta.json()["detalle"] == "La ruta no corresponde a un archivo."


@requiere_ffmpeg
def test_rechaza_registrar_dos_veces_el_mismo_archivo_en_el_proyecto(cliente, generar_video):
    proyecto_id = crear_proyecto(cliente)
    ruta = generar_video("repetido.mp4")
    assert importar_video(cliente, proyecto_id, ruta).status_code == 201

    segunda = importar_video(cliente, proyecto_id, ruta)

    assert segunda.status_code == 409
    assert segunda.json()["detalle"] == "Este video ya está registrado en el proyecto."


@requiere_ffmpeg
def test_permite_el_mismo_archivo_en_otro_proyecto(cliente, generar_video):
    primero = crear_proyecto(cliente, "Uno")
    segundo = crear_proyecto(cliente, "Dos")
    ruta = generar_video("compartido.mp4")

    assert importar_video(cliente, primero, ruta).status_code == 201
    assert importar_video(cliente, segundo, ruta).status_code == 201


@requiere_ffmpeg
def test_rechaza_proyecto_inexistente(cliente, generar_video):
    ruta = generar_video("sin_proyecto.mp4")

    respuesta = importar_video(cliente, 9999, ruta)

    assert respuesta.status_code == 404
    assert respuesta.json()["detalle"] == "El proyecto no existe."


@requiere_ffmpeg
@pytest.mark.parametrize(
    "nombre",
    [
        "vídeo con tildes y ñ.mp4",
        "partida final (versión 2) [HD].mp4",
        "clip #1 & más, 100% listo.mp4",
        "archivo 'comillas' y ;punto y coma.mp4",
    ],
)
def test_importa_rutas_con_espacios_tildes_y_caracteres_especiales(
    cliente, generar_video, nombre
):
    proyecto_id = crear_proyecto(cliente)
    origen = generar_video("base.mp4")
    ruta = origen.parent / nombre
    shutil.copy(origen, ruta)

    respuesta = importar_video(cliente, proyecto_id, ruta)

    assert respuesta.status_code == 201, respuesta.text
    assert respuesta.json()["nombre"] == nombre


@requiere_ffmpeg
def test_importa_ruta_en_carpeta_con_tildes_y_espacios(cliente, generar_video, tmp_path):
    proyecto_id = crear_proyecto(cliente)
    origen = generar_video("base.mp4")
    carpeta = tmp_path / "Mis Videos Ñandú"
    carpeta.mkdir()
    ruta = carpeta / "partida ñ.mp4"
    shutil.copy(origen, ruta)

    respuesta = importar_video(cliente, proyecto_id, ruta)

    assert respuesta.status_code == 201, respuesta.text
    assert respuesta.json()["nombre_archivo"] == "partida ñ.mp4"
    assert str(carpeta) not in respuesta.text


@requiere_ffmpeg
def test_rechaza_enlace_simbolico(cliente, generar_video, tmp_path):
    proyecto_id = crear_proyecto(cliente)
    origen = generar_video("original.mp4")
    enlace = tmp_path / "enlace.mp4"
    try:
        os.symlink(origen, enlace)
    except OSError:
        pytest.skip("El sistema no permite crear enlaces simbólicos sin privilegios")

    respuesta = importar_video(cliente, proyecto_id, enlace)

    assert respuesta.status_code == 422
    assert "enlaces simbólicos" in respuesta.json()["detalle"]


def test_acepta_extension_en_mayusculas(tmp_path):
    archivo = tmp_path / "MAYUSCULAS.MP4"
    archivo.write_bytes(b"contenido")

    assert validar_ruta_entrada(str(archivo)) == archivo


def test_interpreta_fps_fraccionario_de_ntsc():
    datos = {
        "format": {"format_name": "mov,mp4", "duration": "10.0"},
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1920,
                "height": 1080,
                "avg_frame_rate": "30000/1001",
            }
        ],
    }

    metadatos = interpretar_metadatos(datos, tamano_bytes=100)

    assert metadatos.fps == pytest.approx(29.97, abs=0.01)
    assert metadatos.codec_audio is None


def test_fps_invalido_se_reemplaza_por_r_frame_rate():
    datos = {
        "format": {},
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "vp9",
                "width": 640,
                "height": 360,
                "avg_frame_rate": "0/0",
                "r_frame_rate": "24/1",
            }
        ],
    }

    assert interpretar_metadatos(datos, tamano_bytes=1).fps == 24.0


def test_rechaza_archivo_sin_pista_de_video():
    datos = {
        "format": {"format_name": "wav"},
        "streams": [{"codec_type": "audio", "codec_name": "pcm_s16le"}],
    }

    with pytest.raises(SolicitudInvalida, match="pista de video"):
        interpretar_metadatos(datos, tamano_bytes=1)


def test_ignora_caratula_adjunta_como_pista_de_video():
    datos = {
        "format": {"format_name": "mp3"},
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "mjpeg",
                "width": 500,
                "height": 500,
                "disposition": {"attached_pic": 1},
            },
            {"codec_type": "audio", "codec_name": "mp3"},
        ],
    }

    with pytest.raises(SolicitudInvalida, match="pista de video"):
        interpretar_metadatos(datos, tamano_bytes=1)
