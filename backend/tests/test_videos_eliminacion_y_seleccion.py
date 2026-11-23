import base64
import hashlib
from pathlib import Path

import pytest

from app.core import dialogo_archivos
from app.core.dialogo_archivos import seleccionar_video
from app.core.errores import NoDisponible, NoSoportado
from tests.ayudas import crear_proyecto, importar_video
from tests.conftest import requiere_ffmpeg


def _sha256(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


@requiere_ffmpeg
def test_eliminar_registro_no_borra_el_archivo_original(cliente, generar_video):
    proyecto_id = crear_proyecto(cliente)
    ruta = generar_video("original_intacto.mp4", audio=True)
    huella_antes = _sha256(ruta)
    video = importar_video(cliente, proyecto_id, ruta).json()

    respuesta = cliente.delete(f"/api/v1/videos/{video['id']}")

    assert respuesta.status_code == 204
    assert ruta.exists()
    assert _sha256(ruta) == huella_antes
    assert cliente.get(f"/api/v1/videos?proyecto_id={proyecto_id}").json() == []


@requiere_ffmpeg
def test_video_eliminado_ya_no_es_accesible(cliente, generar_video):
    proyecto_id = crear_proyecto(cliente)
    video = importar_video(cliente, proyecto_id, generar_video("borrable.mp4")).json()
    cliente.delete(f"/api/v1/videos/{video['id']}")

    assert cliente.get(f"/api/v1/videos/{video['id']}").status_code == 404
    assert cliente.get(f"/api/v1/videos/{video['id']}/stream").status_code == 404


def test_eliminar_video_inexistente_devuelve_404(cliente):
    respuesta = cliente.delete("/api/v1/videos/777")

    assert respuesta.status_code == 404
    assert respuesta.json()["detalle"] == "El video no existe."


@requiere_ffmpeg
def test_video_original_eliminado_fuera_de_la_app_queda_no_disponible(cliente, generar_video):
    proyecto_id = crear_proyecto(cliente)
    ruta = generar_video("externo.mp4")
    video = importar_video(cliente, proyecto_id, ruta).json()
    ruta.unlink()

    listado = cliente.get(f"/api/v1/videos?proyecto_id={proyecto_id}").json()

    assert listado[0]["id"] == video["id"]
    assert listado[0]["disponible"] is False


@requiere_ffmpeg
def test_listar_exige_proyecto_existente(cliente):
    respuesta = cliente.get("/api/v1/videos?proyecto_id=999")

    assert respuesta.status_code == 404


def test_listar_exige_parametro_proyecto(cliente):
    respuesta = cliente.get("/api/v1/videos")

    assert respuesta.status_code == 422


# Selector nativo: se simula el proceso del sistema. No se abre ningún diálogo real.


class _Resultado:
    def __init__(self, returncode: int, stdout: bytes = b"", stderr: bytes = b"") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_selector_en_windows_usa_powershell_con_script_fijo(monkeypatch):
    capturado = {}

    def falso_run(comando, **kwargs):
        capturado["comando"] = comando
        return _Resultado(0, "C:\\Videos\\Mi partida ñ.mp4\r\n".encode("utf-8"))

    monkeypatch.setattr(dialogo_archivos.subprocess, "run", falso_run)

    ruta = seleccionar_video("windows")

    comando = capturado["comando"]
    assert comando[0] == "powershell.exe"
    assert "-STA" in comando and "-EncodedCommand" in comando
    script = comando[-1]
    codigo = base64.b64decode(script).decode("utf-16-le")
    assert "OpenFileDialog" in codigo
    assert ruta == Path("C:\\Videos\\Mi partida ñ.mp4")


def test_selector_en_windows_cancelado_devuelve_none(monkeypatch):
    monkeypatch.setattr(dialogo_archivos.subprocess, "run", lambda c, **k: _Resultado(0, b""))

    assert seleccionar_video("windows") is None


def test_selector_en_macos_usa_osascript(monkeypatch):
    capturado = {}

    def falso_run(comando, **kwargs):
        capturado["comando"] = comando
        return _Resultado(0, "/Users/ana/Videos/Clip ñ.mov\n".encode("utf-8"))

    monkeypatch.setattr(dialogo_archivos.subprocess, "run", falso_run)

    ruta = seleccionar_video("macos")

    assert capturado["comando"][0] == "osascript"
    assert capturado["comando"][1] == "-e"
    assert "public.movie" in capturado["comando"][2]
    assert ruta == Path("/Users/ana/Videos/Clip ñ.mov")


def test_selector_en_macos_cancelado_devuelve_none(monkeypatch):
    error = b"execution error: User canceled. (-128)"
    monkeypatch.setattr(dialogo_archivos.subprocess, "run", lambda c, **k: _Resultado(1, stderr=error))

    assert seleccionar_video("macos") is None


def test_selector_en_macos_con_otro_error_falla(monkeypatch):
    monkeypatch.setattr(
        dialogo_archivos.subprocess,
        "run",
        lambda c, **k: _Resultado(1, stderr=b"error inesperado"),
    )

    with pytest.raises(NoDisponible):
        seleccionar_video("macos")


def test_selector_en_linux_no_esta_soportado():
    with pytest.raises(NoSoportado):
        seleccionar_video("linux")


def test_selector_no_admite_dos_diálogos_a_la_vez(monkeypatch):
    from app.core.errores import Conflicto

    dialogo_archivos._CANDADO.acquire()
    try:
        with pytest.raises(Conflicto):
            seleccionar_video("windows")
    finally:
        dialogo_archivos._CANDADO.release()


def test_endpoint_de_seleccion_devuelve_null_al_cancelar(cliente, monkeypatch):
    monkeypatch.setattr(
        "app.modules.videos.router.seleccionar_video", lambda sistema: None
    )

    respuesta = cliente.post("/api/v1/videos/seleccion")

    assert respuesta.status_code == 200
    assert respuesta.json() == {"seleccion_id": None, "nombre_archivo": None}


def test_endpoint_de_seleccion_guarda_la_ruta_y_responde_identificador(cliente, monkeypatch, tmp_path):
    elegida = tmp_path / "elegido.mp4"
    monkeypatch.setattr(
        "app.modules.videos.router.seleccionar_video", lambda sistema: elegida
    )

    respuesta = cliente.post("/api/v1/videos/seleccion")

    cuerpo = respuesta.json()
    assert respuesta.status_code == 200
    assert set(cuerpo) == {"seleccion_id", "nombre_archivo"}
    assert cuerpo["nombre_archivo"] == "elegido.mp4"
    assert cuerpo["seleccion_id"]
    assert str(tmp_path) not in respuesta.text


@requiere_ffmpeg
def test_importar_con_seleccion_usa_la_ruta_guardada_una_sola_vez(cliente, monkeypatch, generar_video):
    proyecto_id = crear_proyecto(cliente)
    elegida = generar_video("desde_selector.mp4")
    monkeypatch.setattr(
        "app.modules.videos.router.seleccionar_video", lambda sistema: elegida
    )
    seleccion = cliente.post("/api/v1/videos/seleccion").json()

    primera = cliente.post(
        "/api/v1/videos",
        json={"proyecto_id": proyecto_id, "seleccion_id": seleccion["seleccion_id"]},
    )
    assert primera.status_code == 201, primera.text
    assert primera.json()["nombre_archivo"] == "desde_selector.mp4"

    segunda = cliente.post(
        "/api/v1/videos",
        json={"proyecto_id": proyecto_id, "seleccion_id": seleccion["seleccion_id"]},
    )
    assert segunda.status_code == 422
    assert segunda.json()["detalle"].startswith("La selección caducó")


def test_importar_con_seleccion_desconocida_falla_sin_detalles(cliente):
    proyecto_id = crear_proyecto(cliente)
    respuesta = cliente.post(
        "/api/v1/videos",
        json={"proyecto_id": proyecto_id, "seleccion_id": "no-existe"},
    )
    assert respuesta.status_code == 422
    assert "no-existe" not in respuesta.text


def test_importar_exige_ruta_o_seleccion_pero_no_ambas(cliente):
    proyecto_id = crear_proyecto(cliente)
    ninguna = cliente.post("/api/v1/videos", json={"proyecto_id": proyecto_id})
    ambas = cliente.post(
        "/api/v1/videos",
        json={"proyecto_id": proyecto_id, "ruta": "C:/x.mp4", "seleccion_id": "abc"},
    )
    assert ninguna.status_code == 422
    assert ambas.status_code == 422


def test_subprocess_se_invoca_sin_shell(monkeypatch):
    """Ninguna llamada al sistema puede usar shell=True."""
    llamadas = []

    def falso_run(comando, **kwargs):
        llamadas.append(kwargs)
        return _Resultado(0, b"")

    monkeypatch.setattr(dialogo_archivos.subprocess, "run", falso_run)
    seleccionar_video("windows")

    assert all(not kwargs.get("shell", False) for kwargs in llamadas)
