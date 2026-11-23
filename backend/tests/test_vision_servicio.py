"""Análisis visual con la cola de trabajos, la base SQLite y FFmpeg reales. Requiere FFmpeg y FFprobe."""
import dataclasses
import subprocess
import sys
import time
from pathlib import Path

import pytest

from app.composicion import registrar
from app.core.errores import Conflicto, SolicitudInvalida
from app.core.rutas import RaizDatos
from app.db.conexion import conectar
from app.db.migraciones import aplicar_migraciones
from app.jobs import service as trabajos
from app.jobs.contexto import ContextoTrabajo
from app.jobs.worker import Worker
from app.modules.analisis import service as analisis
from app.modules.projects import service as proyectos
from app.modules.projects.schemas import ProyectoCrear
from app.modules.videos import repository as videos_repo
from app.modules.videos import service as videos
from app.modules.vision import analizador, service as servicio, tarea
from app.plugins.registro import REGISTRO
from tests.conftest import requiere_ffmpeg
from tests.test_vision_analizador import _video_colores

pytestmark = requiere_ffmpeg

TOKEN = "v" * 32


@pytest.fixture(autouse=True)
def _registro_listo():
    registrar()
    yield


@pytest.fixture
def base(tmp_path):
    datos = tmp_path / "datos"
    ruta_db = datos / "clipperai.db"
    conexion = conectar(ruta_db)
    try:
        aplicar_migraciones(conexion)
        proyecto = proyectos.crear(conexion, ProyectoCrear(nombre="Prueba visual")).id
    finally:
        conexion.close()
    return {"datos": datos, "db": ruta_db, "lock": datos / "runtime" / "worker.lock", "proyecto": proyecto}


def _registrar_video(base, ruta: Path, *, duracion: float, con_video: bool = True) -> int:
    conexion = conectar(base["db"])
    try:
        return videos_repo.insertar(
            conexion,
            {
                "proyecto_id": base["proyecto"],
                "nombre": ruta.name,
                "ruta_original": str(ruta),
                "tamano_bytes": ruta.stat().st_size,
                "duracion_segundos": duracion,
                "ancho": 320,
                "alto": 180,
                "fps": 30.0,
                "codec_video": "mpeg4" if con_video else None,
                "codec_audio": None,
                "formato": "mp4",
            },
        )
    finally:
        conexion.close()


def _iniciar(base, video: int) -> int:
    conexion = conectar(base["db"])
    try:
        return servicio.iniciar_analisis(conexion, video)
    finally:
        conexion.close()


def _consulta(base, funcion):
    conexion = conectar(base["db"])
    try:
        return funcion(conexion)
    finally:
        conexion.close()


def _estado(base, video: int) -> str:
    return _consulta(base, lambda c: analisis.obtener_analisis(c, video, analizador.IDENTIFICADOR).estado)


def _esperar(condicion, segundos: float, mensaje: str):
    limite = time.monotonic() + segundos
    while time.monotonic() < limite:
        if condicion():
            return
        time.sleep(0.2)
    raise AssertionError(mensaje)


def _worker(base) -> Worker:
    return Worker(
        base["db"],
        base["lock"],
        RaizDatos(base["datos"]),
        intervalo_sondeo=0.1,
        intervalo_latido=0.3,
        gracia_cancelacion=5.0,
        intervalo_recuperacion=0.5,
    )


def _contexto(base, trabajo: int, token: str, payload: dict) -> ContextoTrabajo:
    conexion = conectar(base["db"])
    directorio = base["datos"] / "runtime" / "trabajos" / str(trabajo)
    return ContextoTrabajo(base["db"], conexion, trabajo, token, payload, directorio, 60.0)


# -- Inicio ---------------------------------------------------------------------------------

def test_iniciar_sin_pista_de_video_se_rechaza(base, tmp_path, monkeypatch):
    # El esquema exige codec_video, así que un video sin pista de vídeo no se puede guardar. La comprobación
    # del servicio protege igualmente el caso de datos incompletos, y se prueba simulando esos datos.
    video = _registrar_video(base, _video_colores(tmp_path / "v.mp4", [("red", 2)]), duracion=2.0)
    datos = videos.datos_para_analisis
    monkeypatch.setattr(
        servicio.videos,
        "datos_para_analisis",
        lambda conexion, video_id: dataclasses.replace(datos(conexion, video_id), tiene_video=False),
    )
    with pytest.raises(SolicitudInvalida):
        _iniciar(base, video)


def test_iniciar_crea_trabajo_con_segmentos_y_deja_el_analisis_en_curso(base, tmp_path):
    video = _registrar_video(base, _video_colores(tmp_path / "v.mp4", [("red", 3), ("blue", 3)]), duracion=6.0)
    trabajo = _iniciar(base, video)
    assert _estado(base, video) == "en_curso"
    segmentos = _consulta(base, lambda c: c.execute(
        "SELECT tipo_analisis, COUNT(*) AS n FROM segmentos_trabajo WHERE trabajo_id = ? GROUP BY tipo_analisis",
        (trabajo,),
    ).fetchall())
    assert {fila["tipo_analisis"]: fila["n"] for fila in segmentos} == {"fotogramas": 1, "cierre": 1}
    with pytest.raises(Conflicto):
        _iniciar(base, video)


# -- Ejecución completa con el worker --------------------------------------------------------

def test_analisis_completo_por_el_worker_persiste_senales_y_fotogramas(base, tmp_path):
    ruta = _video_colores(tmp_path / "corte.mp4", [("red", 3), ("blue", 3)])
    video = _registrar_video(base, ruta, duracion=6.0)
    _iniciar(base, video)
    worker = _worker(base)
    assert worker.iniciar()
    try:
        _esperar(lambda: _estado(base, video) in ("completado", "fallido"), 180, "El análisis no terminó.")
    finally:
        worker.detener()
    assert _estado(base, video) == "completado"

    senales = _consulta(base, lambda c: analisis.listar_senales(c, video, "video", None, None, 2000))
    tipos = {s.tipo for s in senales}
    assert tipos == {"brillo", "movimiento", "cambio_escena"}
    assert len([s for s in senales if s.tipo == "brillo"]) == 6
    cambios = [s for s in senales if s.tipo == "cambio_escena"]
    assert len(cambios) == 1 and cambios[0].inicio_ms <= 3000 <= cambios[0].fin_ms
    fotogramas = _consulta(base, lambda c: analisis.listar_fotogramas(c, video, "video"))
    assert fotogramas, "Debe haber al menos un fotograma representativo."
    for fotograma in fotogramas:
        miniatura = _consulta(base, lambda c: analisis.ruta_miniatura(c, RaizDatos(base["datos"]), video, "video", fotograma.tiempo_ms))
        assert miniatura.is_file()


def test_video_danado_deja_el_analisis_fallido_sin_rutas_en_el_error(base, tmp_path):
    texto = tmp_path / "danado.mp4"
    texto.write_text("no es un video", encoding="utf-8")
    video = _registrar_video(base, texto, duracion=3.0)
    _iniciar(base, video)
    worker = _worker(base)
    assert worker.iniciar()
    try:
        _esperar(lambda: _estado(base, video) == "fallido", 180, "El análisis no falló.")
    finally:
        worker.detener()
    error = _consulta(base, lambda c: analisis.obtener_analisis(c, video, "video").error)
    assert error
    assert str(tmp_path) not in error


def test_cancelar_en_cola_no_deja_senales_ni_fotogramas(base, tmp_path):
    video = _registrar_video(base, _video_colores(tmp_path / "v.mp4", [("red", 3), ("blue", 3)]), duracion=6.0)
    trabajo = _iniciar(base, video)
    conexion = conectar(base["db"])
    try:
        trabajos.cancelar(conexion, trabajo)
    finally:
        conexion.close()
    assert _estado(base, video) == "cancelado"
    contadores = _consulta(base, lambda c: (
        c.execute("SELECT COUNT(*) FROM senales").fetchone()[0],
        c.execute("SELECT COUNT(*) FROM fotogramas").fetchone()[0],
    ))
    assert contadores == (0, 0)


# -- Reanudación ------------------------------------------------------------------------------

def test_reanudar_tras_interrupcion_no_duplica_senales_ni_fotogramas(base, tmp_path):
    ruta = _video_colores(tmp_path / "v.mp4", [("red", 3), ("blue", 3)])
    video = _registrar_video(base, ruta, duracion=6.0)
    trabajo = _iniciar(base, video)
    payload = {"video_id": video, "analizador": "video"}
    directorio_raiz = RaizDatos(base["datos"])

    # Primer intento: procesa el segmento de fotogramas y se interrumpe antes de la siguiente confirmación.
    conexion = conectar(base["db"])
    try:
        assert trabajos.reclamar_siguiente(conexion, "1" * 32) == trabajo
        analisis_id = analisis.id_analisis(conexion, video, "video")
        assert trabajos.marcar_segmento_procesando(conexion, trabajo, "1" * 32, "fotogramas", 0)
        from app.modules.vision.analizador import AnalizadorVideo
        from app.modules.analisis.almacenamiento import AlmacenFotogramasVideo
        from app.plugins.contrato import SegmentoEntrada

        visual = AnalizadorVideo(dimensiones_origen=(320, 180))
        # El plan del trabajo usa la duración del video (6 s), así que el único segmento de fotogramas es [0, 6000).
        resultado = visual.analizar_segmento(
            SegmentoEntrada(ruta, 0, 6000), AlmacenFotogramasVideo(directorio_raiz, video)
        )
        trabajos.confirmar_segmento(
            conexion, trabajo, "1" * 32, "fotogramas", 0, None, None, analizador.VERSION,
            persistir=lambda c: analisis.persistir_resultado(c, directorio_raiz, analisis_id, resultado),
        )
        assert trabajos.reencolar_interrumpido(conexion, trabajo, "1" * 32, max_intentos=3) == "reencolado"
    finally:
        conexion.close()

    # Segundo intento: ejecuta la tarea completa. El segmento confirmado debe saltarse.
    contexto = _contexto(base, trabajo, TOKEN, payload)
    try:
        assert trabajos.reclamar_siguiente(contexto.conexion, TOKEN) == trabajo
        tarea.analisis_video(payload, contexto)
    finally:
        contexto.conexion.close()

    senales = _consulta(base, lambda c: analisis.listar_senales(c, video, "video", None, None, 2000))
    claves = [(s.tipo, s.inicio_ms, s.fin_ms) for s in senales]
    assert len(claves) == len(set(claves))
    assert len([s for s in senales if s.tipo == "brillo"]) == 6
    assert len([s for s in senales if s.tipo == "movimiento"]) == 5
    fotogramas = _consulta(base, lambda c: analisis.listar_fotogramas(c, video, "video"))
    tiempos = [f.tiempo_ms for f in fotogramas]
    assert len(tiempos) == len(set(tiempos))
    assert _estado(base, video) == "completado"


# -- Seguridad de rutas -------------------------------------------------------------------------

def test_directorio_de_miniaturas_enlazado_fuera_de_datos_no_recibe_archivos(base, tmp_path):
    if sys.platform != "win32":
        pytest.skip("La prueba usa un junction de Windows, que no requiere privilegios.")
    ruta = _video_colores(tmp_path / "v.mp4", [("red", 3), ("blue", 3)])
    video = _registrar_video(base, ruta, duracion=6.0)
    fuera = tmp_path / "fuera"
    fuera.mkdir()
    trabajos_work = base["datos"] / "work" / str(video)
    trabajos_work.mkdir(parents=True)
    enlace = trabajos_work / "fotogramas"
    subprocess.run(["cmd", "/c", "mklink", "/J", str(enlace), str(fuera)], check=True, capture_output=True)
    try:
        _iniciar(base, video)
        worker = _worker(base)
        assert worker.iniciar()
        try:
            _esperar(lambda: _estado(base, video) in ("completado", "fallido"), 180, "El análisis no terminó.")
        finally:
            worker.detener()
        assert list(fuera.iterdir()) == []
    finally:
        if enlace.exists():
            subprocess.run(["cmd", "/c", "rmdir", str(enlace)], check=False, capture_output=True)
