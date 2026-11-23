from fastapi.testclient import TestClient

from app.core.rutas import RaizDatos
from app.db.conexion import conectar
from app.main import ENCABEZADO_TOKEN
from app.modules.analisis import service as analisis
from app.modules.analisis.almacenamiento import AlmacenFotogramasVideo
from app.plugins.contrato import ResultadoSegmento, Senal
from tests.ayudas import JPEG_PRUEBA, AnalizadorFalso, crear_proyecto, insertar_video_directo, persistir_en_transaccion, registro_con

BASE = "/api/v1/videos"


def _video_con_analisis(cliente, configuracion) -> int:
    """Crea un video con un análisis de audio completado y dos señales, y una miniatura. Sin FFmpeg."""
    proyecto = crear_proyecto(cliente)
    conexion = conectar(configuracion.ruta_base_datos)
    try:
        video = insertar_video_directo(conexion, proyecto)
        raiz = RaizDatos(configuracion.data_dir)
        registro = registro_con(AnalizadorFalso("audio", "1"))
        analisis_fila = analisis.preparar_analisis(conexion, video, "audio", registro)
        miniatura = AlmacenFotogramasVideo(raiz, video).guardar(1000, JPEG_PRUEBA)
        persistir_en_transaccion(
            conexion,
            raiz,
            analisis_fila.id,
            ResultadoSegmento(
                senales=(
                    Senal(tipo="energia_audio", inicio_ms=0, fin_ms=1000, valor=0.3, confianza=0.9),
                    Senal(tipo="escena", inicio_ms=4000, fin_ms=5000, valor=0.8, confianza=0.7),
                ),
                fotogramas=(miniatura,),
            ),
        )
        analisis.marcar_estado(conexion, analisis_fila.id, "completado")
        return video
    finally:
        conexion.close()


def test_sin_token_valido_se_rechaza(cliente, configuracion):
    video = _video_con_analisis(cliente, configuracion)
    cliente.headers[ENCABEZADO_TOKEN] = "token-incorrecto"
    assert cliente.get(f"{BASE}/{video}/analisis").status_code == 401


def test_sin_cabecera_de_token_se_rechaza(cliente, configuracion):
    video = _video_con_analisis(cliente, configuracion)
    sin_token = TestClient(cliente.app, base_url="http://127.0.0.1:8000")  # Sin lifespan: no regenera el token.
    assert sin_token.get(f"{BASE}/{video}/analisis").status_code == 401


def test_origen_no_permitido_se_rechaza_antes_de_llegar_a_los_datos(cliente, configuracion):
    video = _video_con_analisis(cliente, configuracion)
    respuesta = cliente.get(f"{BASE}/{video}/analisis", headers={"Origin": "http://evil.example"})
    assert respuesta.status_code == 403


def test_video_inexistente_responde_404(cliente):
    assert cliente.get(f"{BASE}/999/analisis").status_code == 404


def test_video_sin_analisis_devuelve_lista_vacia(cliente, configuracion):
    proyecto = crear_proyecto(cliente)
    conexion = conectar(configuracion.ruta_base_datos)
    try:
        video = insertar_video_directo(conexion, proyecto)
    finally:
        conexion.close()
    respuesta = cliente.get(f"{BASE}/{video}/analisis")
    assert respuesta.status_code == 200
    assert respuesta.json() == []


def test_lista_de_analisis_no_expone_rutas(cliente, configuracion):
    video = _video_con_analisis(cliente, configuracion)
    respuesta = cliente.get(f"{BASE}/{video}/analisis")
    assert respuesta.status_code == 200
    datos = respuesta.json()
    assert [(a["analizador"], a["estado"], a["version_analizador"]) for a in datos] == [("audio", "completado", "1")]
    assert set(datos[0]) == {"id", "video_id", "analizador", "version_analizador", "estado", "error", "creado", "actualizado"}
    assert str(configuracion.data_dir) not in respuesta.text


def test_obtener_un_analisis(cliente, configuracion):
    video = _video_con_analisis(cliente, configuracion)
    respuesta = cliente.get(f"{BASE}/{video}/analisis/audio")
    assert respuesta.status_code == 200
    assert respuesta.json()["estado"] == "completado"


def test_analisis_de_un_analizador_sin_resultados_responde_404(cliente, configuracion):
    video = _video_con_analisis(cliente, configuracion)
    assert cliente.get(f"{BASE}/{video}/analisis/vision").status_code == 404


def test_senales_devuelven_solo_las_que_se_solapan(cliente, configuracion):
    video = _video_con_analisis(cliente, configuracion)
    respuesta = cliente.get(f"{BASE}/{video}/analisis/audio/senales", params={"inicio_ms": 0, "fin_ms": 500})
    assert respuesta.status_code == 200
    assert [s["tipo"] for s in respuesta.json()] == ["energia_audio"]
    assert set(respuesta.json()[0]) == {"tipo", "inicio_ms", "fin_ms", "valor", "confianza"}


def test_senales_sin_intervalo_devuelven_todas(cliente, configuracion):
    video = _video_con_analisis(cliente, configuracion)
    respuesta = cliente.get(f"{BASE}/{video}/analisis/audio/senales")
    assert [s["inicio_ms"] for s in respuesta.json()] == [0, 4000]


def test_senales_rechazan_intervalo_invertido(cliente, configuracion):
    video = _video_con_analisis(cliente, configuracion)
    respuesta = cliente.get(f"{BASE}/{video}/analisis/audio/senales", params={"inicio_ms": 900, "fin_ms": 100})
    assert respuesta.status_code == 422


def test_senales_rechazan_tiempos_negativos_y_limites_fuera_de_rango(cliente, configuracion):
    video = _video_con_analisis(cliente, configuracion)
    base = f"{BASE}/{video}/analisis/audio/senales"
    assert cliente.get(base, params={"inicio_ms": -1}).status_code == 422
    assert cliente.get(base, params={"limite": 0}).status_code == 422
    assert cliente.get(base, params={"limite": 2001}).status_code == 422
    assert cliente.get(base, params={"inicio_ms": "1.5"}).status_code == 422


def test_analizador_con_formato_no_valido_se_rechaza(cliente, configuracion):
    video = _video_con_analisis(cliente, configuracion)
    assert cliente.get(f"{BASE}/{video}/analisis/Audio").status_code == 422
    assert cliente.get(f"{BASE}/{video}/analisis/..%2Fcosas").status_code in (404, 422)


def test_fotogramas_listan_sus_tiempos(cliente, configuracion):
    video = _video_con_analisis(cliente, configuracion)
    respuesta = cliente.get(f"{BASE}/{video}/analisis/audio/fotogramas")
    assert respuesta.status_code == 200
    assert respuesta.json() == [{"tiempo_ms": 1000}]


def test_miniatura_se_sirve_como_jpeg_sin_cache(cliente, configuracion):
    video = _video_con_analisis(cliente, configuracion)
    respuesta = cliente.get(f"{BASE}/{video}/analisis/audio/fotogramas/1000/miniatura")
    assert respuesta.status_code == 200
    assert respuesta.headers["content-type"] == "image/jpeg"
    assert respuesta.headers["cache-control"] == "no-store"
    assert respuesta.content == JPEG_PRUEBA


def test_miniatura_inexistente_responde_404_sin_rutas(cliente, configuracion):
    video = _video_con_analisis(cliente, configuracion)
    respuesta = cliente.get(f"{BASE}/{video}/analisis/audio/fotogramas/5000/miniatura")
    assert respuesta.status_code == 404
    assert str(configuracion.data_dir) not in respuesta.text


def test_miniatura_con_tiempo_negativo_se_rechaza(cliente, configuracion):
    video = _video_con_analisis(cliente, configuracion)
    assert cliente.get(f"{BASE}/{video}/analisis/audio/fotogramas/-1/miniatura").status_code == 422


def test_miniatura_con_fila_que_apunta_fuera_del_almacen_no_se_sirve(cliente, configuracion):
    video = _video_con_analisis(cliente, configuracion)
    conexion = conectar(configuracion.ruta_base_datos)
    try:
        conexion.execute(
            "UPDATE fotogramas SET ruta_relativa = 'clipperai.db' WHERE tiempo_ms = 1000"
        )
        conexion.commit()
    finally:
        conexion.close()
    respuesta = cliente.get(f"{BASE}/{video}/analisis/audio/fotogramas/1000/miniatura")
    assert respuesta.status_code == 404
    assert b"SQLite" not in respuesta.content


def test_la_api_de_analisis_es_solo_de_lectura(cliente, configuracion):
    video = _video_con_analisis(cliente, configuracion)
    assert cliente.post(f"{BASE}/{video}/analisis", json={}).status_code == 405
    assert cliente.delete(f"{BASE}/{video}/analisis/audio").status_code == 405
    assert cliente.post(f"{BASE}/{video}/analisis/audio/senales", json={}).status_code == 405


def test_eliminar_el_video_elimina_sus_analisis(cliente, configuracion):
    video = _video_con_analisis(cliente, configuracion)
    assert cliente.delete(f"{BASE}/{video}").status_code == 204
    assert cliente.get(f"{BASE}/{video}/analisis").status_code == 404
    conexion = conectar(configuracion.ruta_base_datos)
    try:
        assert conexion.execute("SELECT COUNT(*) FROM senales").fetchone()[0] == 0
    finally:
        conexion.close()
