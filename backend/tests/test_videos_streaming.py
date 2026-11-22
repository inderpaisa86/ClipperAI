import pytest

from app.modules.videos.streaming import (
    RangoBytes,
    RangoNoSatisfacible,
    interpretar_rango,
    iterar_archivo,
)
from tests.ayudas import crear_proyecto, importar_video
from tests.conftest import requiere_ffmpeg


@pytest.fixture
def video_importado(cliente, generar_video):
    proyecto_id = crear_proyecto(cliente)
    ruta = generar_video("transmision.mp4", audio=True)
    respuesta = importar_video(cliente, proyecto_id, ruta)
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json(), ruta


@requiere_ffmpeg
def test_transmite_archivo_completo_sin_cabecera_range(cliente, video_importado):
    video, ruta = video_importado

    respuesta = cliente.get(f"/api/v1/videos/{video['id']}/stream")

    assert respuesta.status_code == 200
    assert respuesta.headers["accept-ranges"] == "bytes"
    assert respuesta.headers["content-length"] == str(ruta.stat().st_size)
    assert respuesta.headers["content-type"] == "video/mp4"
    assert respuesta.content == ruta.read_bytes()


@requiere_ffmpeg
def test_responde_206_con_rango_inicial(cliente, video_importado):
    video, ruta = video_importado

    respuesta = cliente.get(
        f"/api/v1/videos/{video['id']}/stream", headers={"Range": "bytes=0-99"}
    )

    assert respuesta.status_code == 206
    assert respuesta.headers["content-range"] == f"bytes 0-99/{ruta.stat().st_size}"
    assert respuesta.headers["content-length"] == "100"
    assert respuesta.content == ruta.read_bytes()[:100]


@requiere_ffmpeg
def test_responde_206_con_rango_abierto_hasta_el_final(cliente, video_importado):
    video, ruta = video_importado
    tamano = ruta.stat().st_size
    inicio = tamano - 500

    respuesta = cliente.get(
        f"/api/v1/videos/{video['id']}/stream", headers={"Range": f"bytes={inicio}-"}
    )

    assert respuesta.status_code == 206
    assert respuesta.content == ruta.read_bytes()[inicio:]


@requiere_ffmpeg
def test_responde_206_con_sufijo(cliente, video_importado):
    video, ruta = video_importado

    respuesta = cliente.get(
        f"/api/v1/videos/{video['id']}/stream", headers={"Range": "bytes=-64"}
    )

    assert respuesta.status_code == 206
    assert respuesta.content == ruta.read_bytes()[-64:]


@requiere_ffmpeg
def test_rango_fuera_del_archivo_devuelve_416(cliente, video_importado):
    video, ruta = video_importado
    tamano = ruta.stat().st_size

    respuesta = cliente.get(
        f"/api/v1/videos/{video['id']}/stream", headers={"Range": f"bytes={tamano + 10}-"}
    )

    assert respuesta.status_code == 416
    assert respuesta.headers["content-range"] == f"bytes */{tamano}"


@requiere_ffmpeg
def test_varios_rangos_se_sirven_como_archivo_completo(cliente, video_importado):
    video, ruta = video_importado

    respuesta = cliente.get(
        f"/api/v1/videos/{video['id']}/stream", headers={"Range": "bytes=0-10, 20-30"}
    )

    assert respuesta.status_code == 200
    assert respuesta.content == ruta.read_bytes()


def test_stream_de_video_inexistente_devuelve_404(cliente):
    respuesta = cliente.get("/api/v1/videos/4242/stream")

    assert respuesta.status_code == 404


@requiere_ffmpeg
def test_stream_falla_si_el_original_desaparece(cliente, video_importado):
    video, ruta = video_importado
    ruta.unlink()

    respuesta = cliente.get(f"/api/v1/videos/{video['id']}/stream")

    assert respuesta.status_code == 404
    assert respuesta.json()["detalle"] == "El archivo original ya no está disponible."


# Pruebas unitarias del parser de Range. No requieren FFmpeg.


@pytest.mark.parametrize(
    ("cabecera", "esperado"),
    [
        ("bytes=0-99", RangoBytes(0, 99)),
        ("bytes=100-", RangoBytes(100, 999)),
        ("bytes=-50", RangoBytes(950, 999)),
        ("bytes=0-5000", RangoBytes(0, 999)),
        ("BYTES=10-20", RangoBytes(10, 20)),
        ("bytes = 5-7", RangoBytes(5, 7)),
    ],
)
def test_interpreta_rangos_validos(cabecera, esperado):
    assert interpretar_rango(cabecera, tamano=1000) == esperado


@pytest.mark.parametrize("cabecera", [None, "", "items=0-9", "bytes=0-1,4-5"])
def test_ignora_cabeceras_que_no_piden_un_rango_simple(cabecera):
    assert interpretar_rango(cabecera, tamano=1000) is None


@pytest.mark.parametrize(
    "cabecera",
    [
        "bytes=abc",
        "bytes=-",
        "bytes=-0",
        "bytes=1000-",
        "bytes=50-10",
        "bytes=5000-6000",
    ],
)
def test_rechaza_rangos_no_satisfacibles(cabecera):
    with pytest.raises(RangoNoSatisfacible):
        interpretar_rango(cabecera, tamano=1000)


def test_rango_sobre_archivo_vacio_no_satisfacible():
    with pytest.raises(RangoNoSatisfacible):
        interpretar_rango("bytes=0-1", tamano=0)


def test_iterar_archivo_grande_entrega_bloques_acotados(tmp_path):
    """Archivo de 300 MB escrito como disperso. Verifica que nunca se lee de una vez."""
    archivo = tmp_path / "grande.bin"
    tamano = 300 * 1024 * 1024
    with open(archivo, "wb") as salida:
        salida.truncate(tamano)

    bloques = list(iterar_archivo(archivo, 0, tamano - 1))

    assert max(len(bloque) for bloque in bloques) <= 1024 * 1024
    assert sum(len(bloque) for bloque in bloques) == tamano


def test_iterar_archivo_respeta_inicio_y_fin(tmp_path):
    archivo = tmp_path / "datos.bin"
    archivo.write_bytes(bytes(range(256)) * 4)

    contenido = b"".join(iterar_archivo(archivo, 300, 399))

    assert contenido == (bytes(range(256)) * 4)[300:400]


def test_rango_grande_con_enteros_mayores_a_32_bits():
    tamano = 6 * 1024**3
    rango = interpretar_rango("bytes=5368709120-", tamano)

    assert rango == RangoBytes(5368709120, tamano - 1)
