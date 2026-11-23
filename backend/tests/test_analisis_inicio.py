"""Inicio de análisis por la API: duplicados, completados, reintentos, rechazos y cancelación en cola."""

from pathlib import Path

from app.db.conexion import conectar
from app.jobs import service as trabajos
from app.modules.analisis import service as analisis
from tests.ayudas import crear_proyecto, insertar_video_directo

BASE = "/api/v1/videos"


def _video(cliente, configuracion, *, audio: bool = True, con_archivo: bool = True) -> int:
    """Video registrado con un archivo real (sin decodificar) y metadatos de audio según `audio`."""
    proyecto = crear_proyecto(cliente)
    original = configuracion.data_dir.parent / f"medio_{proyecto}_{audio}_{con_archivo}.mp4"
    original.parent.mkdir(parents=True, exist_ok=True)
    original.write_bytes(b"contenido de prueba")
    conexion = conectar(configuracion.ruta_base_datos)
    try:
        video = insertar_video_directo(conexion, proyecto)
        conexion.execute(
            "UPDATE videos SET ruta_original = ?, duracion_segundos = 3.0, codec_audio = ? WHERE id = ?",
            (str(original), "aac" if audio else None, video),
        )
        conexion.commit()
        if not con_archivo:
            original.unlink()
    finally:
        conexion.close()
    return video


def _contar_trabajos(configuracion) -> int:
    conexion = conectar(configuracion.ruta_base_datos)
    try:
        return conexion.execute("SELECT COUNT(*) FROM trabajos").fetchone()[0]
    finally:
        conexion.close()


def _accion(respuesta, analizador: str = "audio") -> dict:
    return next(item for item in respuesta.json() if item["analizador"] == analizador)


def test_inicio_crea_un_trabajo_en_cola_y_responde_202(cliente, configuracion):
    video = _video(cliente, configuracion)
    respuesta = cliente.post(f"{BASE}/{video}/analisis")
    assert respuesta.status_code == 202, respuesta.text
    item = _accion(respuesta)
    assert item["accion"] == "iniciado"
    assert isinstance(item["trabajo_id"], int)
    assert item["estado"] == "en_cola"
    assert cliente.get(f"{BASE}/{video}/analisis/audio").json()["estado"] == "en_curso"
    assert _contar_trabajos(configuracion) == 1


def test_segundo_inicio_no_duplica_el_trabajo_activo(cliente, configuracion):
    video = _video(cliente, configuracion)
    primero = _accion(cliente.post(f"{BASE}/{video}/analisis"))
    segundo = _accion(cliente.post(f"{BASE}/{video}/analisis"))
    assert segundo["accion"] == "en_curso"
    assert segundo["trabajo_id"] == primero["trabajo_id"]
    assert _contar_trabajos(configuracion) == 1


def test_analisis_completado_con_la_version_vigente_no_se_repite(cliente, configuracion):
    video = _video(cliente, configuracion)
    primero = _accion(cliente.post(f"{BASE}/{video}/analisis"))
    conexion = conectar(configuracion.ruta_base_datos)
    try:
        analisis_id = analisis.id_analisis(conexion, video, "audio")
        analisis.marcar_estado(conexion, analisis_id, "completado")
    finally:
        conexion.close()
    despues = _accion(cliente.post(f"{BASE}/{video}/analisis"))
    assert despues["accion"] == "sin_cambios"
    assert despues["trabajo_id"] is None
    assert _contar_trabajos(configuracion) == 1
    assert primero["trabajo_id"] is not None


def test_analisis_fallido_se_reintenta_con_un_trabajo_nuevo(cliente, configuracion):
    video = _video(cliente, configuracion)
    primero = _accion(cliente.post(f"{BASE}/{video}/analisis"))
    conexion = conectar(configuracion.ruta_base_datos)
    try:
        analisis_id = analisis.id_analisis(conexion, video, "audio")
        analisis.marcar_estado(conexion, analisis_id, "fallido", primero["trabajo_id"], "Fallo de prueba.")
    finally:
        conexion.close()
    reintento = _accion(cliente.post(f"{BASE}/{video}/analisis"))
    assert reintento["accion"] == "iniciado"
    assert reintento["trabajo_id"] != primero["trabajo_id"]
    assert cliente.get(f"{BASE}/{video}/analisis/audio").json()["estado"] == "en_curso"


def test_video_inexistente_responde_404(cliente):
    respuesta = cliente.post(f"{BASE}/987654/analisis")
    assert respuesta.status_code == 404


def test_video_cuyo_archivo_no_esta_disponible_responde_409(cliente, configuracion):
    video = _video(cliente, configuracion, con_archivo=False)
    respuesta = cliente.post(f"{BASE}/{video}/analisis")
    assert respuesta.status_code == 409
    assert _contar_trabajos(configuracion) == 0


def test_video_sin_audio_se_rechaza_sin_crear_trabajo(cliente, configuracion):
    video = _video(cliente, configuracion, audio=False)
    respuesta = cliente.post(f"{BASE}/{video}/analisis")
    assert respuesta.status_code == 202
    item = _accion(respuesta)
    assert item["accion"] == "rechazado"
    assert "audio" in item["detalle"]
    assert _contar_trabajos(configuracion) == 0


def test_cancelar_en_cola_deja_el_analisis_cancelado_persistido_y_permite_reintentar(cliente, configuracion):
    video = _video(cliente, configuracion)
    trabajo = _accion(cliente.post(f"{BASE}/{video}/analisis"))["trabajo_id"]

    cancelacion = cliente.post(f"/api/v1/jobs/{trabajo}/cancelacion")
    assert cancelacion.status_code == 202
    assert cancelacion.json()["estado"] == "cancelado"

    conexion = conectar(configuracion.ruta_base_datos)
    try:
        fila = conexion.execute(
            "SELECT estado, error FROM analisis WHERE video_id = ? AND analizador = 'audio'", (video,)
        ).fetchone()
    finally:
        conexion.close()
    assert fila["estado"] == "cancelado"
    assert fila["error"] == "Análisis cancelado."

    reintento = _accion(cliente.post(f"{BASE}/{video}/analisis"))
    assert reintento["accion"] == "iniciado"
    assert reintento["trabajo_id"] != trabajo


def test_cancelar_dos_veces_es_idempotente(cliente, configuracion):
    video = _video(cliente, configuracion)
    trabajo = _accion(cliente.post(f"{BASE}/{video}/analisis"))["trabajo_id"]
    assert cliente.post(f"/api/v1/jobs/{trabajo}/cancelacion").status_code == 202
    assert cliente.post(f"/api/v1/jobs/{trabajo}/cancelacion").status_code == 202
    assert cliente.get(f"/api/v1/jobs/{trabajo}").json()["estado"] == "cancelado"


def test_cancelar_un_trabajo_no_audio_no_cambia_analisis_de_audio(cliente, configuracion):
    video = _video(cliente, configuracion)
    conexion = conectar(configuracion.ruta_base_datos)
    try:
        otro = trabajos.crear(conexion, "diagnostico_espera", {"segundos": 0.1})
    finally:
        conexion.close()
    assert cliente.post(f"/api/v1/jobs/{otro}/cancelacion").status_code == 202
    assert cliente.get(f"{BASE}/{video}/analisis").json() == []


def test_filtro_de_senales_por_tipo_y_rechazo_de_tipo_fuera_del_vocabulario(cliente, configuracion):
    from app.plugins.contrato import ResultadoSegmento, Senal
    from tests.ayudas import AnalizadorFalso, persistir_en_transaccion, registro_con
    from app.core.rutas import RaizDatos

    video = _video(cliente, configuracion)
    conexion = conectar(configuracion.ruta_base_datos)
    try:
        fila = analisis.preparar_analisis(conexion, video, "audio", registro_con(AnalizadorFalso("audio", "1")))
        persistir_en_transaccion(
            conexion,
            RaizDatos(configuracion.data_dir),
            fila.id,
            ResultadoSegmento(
                senales=(
                    Senal(tipo="silencio", inicio_ms=0, fin_ms=1000, valor=0.5, confianza=1.0),
                    Senal(tipo="energia_audio", inicio_ms=0, fin_ms=200, valor=0.4, confianza=1.0),
                ),
            ),
        )
    finally:
        conexion.close()

    solo = cliente.get(f"{BASE}/{video}/analisis/audio/senales", params={"tipo": "silencio"}).json()
    assert [s["tipo"] for s in solo] == ["silencio"]
    assert cliente.get(f"{BASE}/{video}/analisis/audio/senales", params={"tipo": "escena"}).status_code == 422
    assert cliente.get(f"{BASE}/{video}/analisis/audio/senales", params={"tipo": "SILENCIO"}).status_code == 422
