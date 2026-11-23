"""Estados finales coherentes de trabajo y análisis según el motivo de terminación.

Pruebas unitarias del servicio de trabajos con un análisis de audio real en la base temporal.
La prueba con worker y proceso hijo reales está en test_audio_cancelacion_real.py.
"""

import pytest

from app.composicion import registrar
from app.core.rutas import RaizDatos
from app.db.conexion import conectar
from app.db.migraciones import aplicar_migraciones
from app.jobs import service as trabajos
from app.modules.analisis import service as analisis
from app.modules.audio import service as audio
from app.modules.projects import service as proyectos
from app.modules.projects.schemas import ProyectoCrear
from app.modules.videos import repository as videos_repo
from app.plugins.contrato import ResultadoSegmento, Senal
from tests.ayudas import persistir_en_transaccion

TOKEN = "t" * 32


@pytest.fixture
def base(tmp_path):
    registrar()
    datos = tmp_path / "datos"
    ruta_db = datos / "clipperai.db"
    conexion = conectar(ruta_db)
    try:
        aplicar_migraciones(conexion)
        proyecto = proyectos.crear(conexion, ProyectoCrear(nombre="Cancelación")).id
        original = tmp_path / "medio.m4a"
        original.write_bytes(b"x")
        video = videos_repo.insertar(
            conexion,
            {
                "proyecto_id": proyecto,
                "nombre": original.name,
                "ruta_original": str(original),
                "tamano_bytes": 1,
                "duracion_segundos": 3.0,
                "ancho": 16,
                "alto": 16,
                "fps": 1.0,
                "codec_video": "h264",
                "codec_audio": "aac",
                "formato": "mp4",
            },
        )
    finally:
        conexion.close()
    return {"db": ruta_db, "datos": datos, "video": video}


def _iniciar_y_reclamar(conexion, base) -> int:
    trabajo = audio.iniciar_analisis(conexion, base["video"])
    assert trabajos.reclamar_siguiente(conexion, TOKEN) == trabajo
    return trabajo


def _con_senales(conexion, base, trabajo_id: int) -> None:
    """Simula dos segmentos ya confirmados: sus señales quedan escritas en la base."""
    analisis_id = analisis.id_analisis(conexion, base["video"], "audio")
    persistir_en_transaccion(
        conexion,
        RaizDatos(base["datos"]),
        analisis_id,
        ResultadoSegmento(
            senales=(
                Senal(tipo="energia_audio", inicio_ms=0, fin_ms=200, valor=0.5, confianza=1.0),
                Senal(tipo="energia_audio", inicio_ms=200, fin_ms=400, valor=0.4, confianza=1.0),
            )
        ),
    )


def _estado(conexion, base) -> tuple[str, str | None, int]:
    fila = conexion.execute(
        "SELECT estado, error FROM analisis WHERE video_id = ? AND analizador = 'audio'", (base["video"],)
    ).fetchone()
    senales = conexion.execute(
        "SELECT COUNT(*) FROM senales s JOIN analisis a ON a.id = s.analisis_id "
        "WHERE a.video_id = ? AND a.analizador = 'audio'",
        (base["video"],),
    ).fetchone()[0]
    return fila["estado"], fila["error"], senales


def test_cancelacion_forzada_por_el_supervisor_cancela_trabajo_y_analisis(base):
    conexion = conectar(base["db"])
    try:
        trabajo = _iniciar_y_reclamar(conexion, base)
        _con_senales(conexion, base, trabajo)
        trabajos.cancelar(conexion, trabajo)  # Cancelación pedida mientras ejecuta: solo marca la solicitud.
        resultado = trabajos.cerrar_tras_proceso(conexion, trabajo, TOKEN, None, "cancelacion_forzada")
        assert resultado == "cancelado"
        assert trabajos.consultar(conexion, trabajo)["estado"] == "cancelado"
        estado, error, senales = _estado(conexion, base)
    finally:
        conexion.close()
    assert estado == "cancelado"
    assert error == "Análisis cancelado."
    assert senales == 0  # Un análisis cancelado no conserva señales parciales (D-057).


def test_parada_con_cancelacion_pedida_cancela_trabajo_y_analisis(base):
    conexion = conectar(base["db"])
    try:
        trabajo = _iniciar_y_reclamar(conexion, base)
        trabajos.cancelar(conexion, trabajo)
        assert trabajos.cerrar_tras_proceso(conexion, trabajo, TOKEN, None, "parada") == "cancelado"
        assert _estado(conexion, base)[0] == "cancelado"
    finally:
        conexion.close()


def test_parada_sin_cancelacion_reencola_y_el_analisis_sigue_en_curso(base):
    conexion = conectar(base["db"])
    try:
        trabajo = _iniciar_y_reclamar(conexion, base)
        assert trabajos.cerrar_tras_proceso(conexion, trabajo, TOKEN, None, "parada") == "reencolado"
        assert trabajos.consultar(conexion, trabajo)["estado"] == "en_cola"
        # El trabajo sigue activo: el análisis no se cierra.
        assert _estado(conexion, base)[0] == "en_curso"
    finally:
        conexion.close()


def test_salida_con_cancelacion_pedida_sin_resultado_es_un_fallo_y_no_una_cancelacion(base):
    """Un error real no se clasifica como cancelación aunque hubiera una cancelación pedida."""
    conexion = conectar(base["db"])
    try:
        trabajo = _iniciar_y_reclamar(conexion, base)
        _con_senales(conexion, base, trabajo)
        trabajos.cancelar(conexion, trabajo)
        assert trabajos.cerrar_tras_proceso(conexion, trabajo, TOKEN, 0, "salida") == "fallido"
        respuesta = trabajos.consultar(conexion, trabajo)
        estado, error, senales = _estado(conexion, base)
    finally:
        conexion.close()
    assert respuesta["estado"] == "fallido"
    assert estado == "fallido"
    assert "sin confirmar el resultado" in error
    # Un fallo conserva los segmentos confirmados (D-044): el reintento con la misma versión los reutiliza.
    assert senales == 2


def test_salida_con_error_sin_cancelacion_falla_el_analisis(base):
    conexion = conectar(base["db"])
    try:
        trabajo = _iniciar_y_reclamar(conexion, base)
        assert trabajos.cerrar_tras_proceso(conexion, trabajo, TOKEN, 1, "salida") == "fallido"
        estado, error, _ = _estado(conexion, base)
    finally:
        conexion.close()
    assert estado == "fallido"
    assert "código 1" in error


def test_cancelacion_en_cola_limpia_senales_y_deja_cancelado(base):
    conexion = conectar(base["db"])
    try:
        trabajo = audio.iniciar_analisis(conexion, base["video"])
        _con_senales(conexion, base, trabajo)
        trabajos.cancelar(conexion, trabajo)
        estado, error, senales = _estado(conexion, base)
    finally:
        conexion.close()
    assert (estado, error, senales) == ("cancelado", "Análisis cancelado.", 0)


def test_motivo_de_terminacion_desconocido_se_rechaza(base):
    conexion = conectar(base["db"])
    try:
        trabajo = _iniciar_y_reclamar(conexion, base)
        with pytest.raises(ValueError):
            trabajos.cerrar_tras_proceso(conexion, trabajo, TOKEN, None, "desconocido")
    finally:
        conexion.close()


def test_cerrar_dos_veces_no_cambia_el_resultado(base):
    conexion = conectar(base["db"])
    try:
        trabajo = _iniciar_y_reclamar(conexion, base)
        _con_senales(conexion, base, trabajo)
        trabajos.cancelar(conexion, trabajo)
        assert trabajos.cerrar_tras_proceso(conexion, trabajo, TOKEN, None, "cancelacion_forzada") == "cancelado"
        assert trabajos.cerrar_tras_proceso(conexion, trabajo, TOKEN, None, "cancelacion_forzada") == "ya_cerrado"
        assert _estado(conexion, base)[0] == "cancelado"
    finally:
        conexion.close()
