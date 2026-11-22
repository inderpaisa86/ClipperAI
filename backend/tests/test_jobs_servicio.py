import threading
from pathlib import Path

import pytest

from app.core.errores import NoEncontrado, SolicitudInvalida
from app.db.conexion import conectar
from app.db.migraciones import aplicar_migraciones
from app.jobs import service
from app.jobs.service import ReclamoPerdido, TrabajoCancelado


@pytest.fixture
def ruta_db(tmp_path: Path) -> Path:
    ruta = tmp_path / "datos" / "clipperai.db"
    conexion = conectar(ruta)
    try:
        aplicar_migraciones(conexion)
    finally:
        conexion.close()
    return ruta


@pytest.fixture
def conexion(ruta_db: Path):
    conexion = conectar(ruta_db)
    yield conexion
    conexion.close()


def test_crear_y_consultar_trabajo(conexion):
    trabajo_id = service.crear(
        conexion, "diagnostico_espera", {"segundos": 1}, [("audio", 0, 0, 300_000)]
    )
    respuesta = service.consultar(conexion, trabajo_id)
    assert respuesta["estado"] == "en_cola"
    assert respuesta["cancelacion_solicitada"] is False
    assert respuesta["intentos"] == 0
    assert "claim_token" not in respuesta and "pid" not in respuesta


def test_tipo_desconocido_se_rechaza(conexion):
    with pytest.raises(SolicitudInvalida):
        service.crear(conexion, "tipo_inexistente", {})


def test_payload_demasiado_grande_se_rechaza(conexion):
    with pytest.raises(SolicitudInvalida):
        service.crear(conexion, "diagnostico_espera", {"relleno": "x" * (service.PAYLOAD_MAXIMO_BYTES + 1)})


def test_trabajo_inexistente(conexion):
    with pytest.raises(NoEncontrado):
        service.consultar(conexion, 999)


def test_reclamo_concurrente_solo_gana_uno(ruta_db):
    conexion = conectar(ruta_db)
    try:
        trabajo_id = service.crear(conexion, "diagnostico_espera", {})
    finally:
        conexion.close()

    participantes = 8
    barrera = threading.Barrier(participantes)
    resultados: list[int | None] = []
    cerrojo = threading.Lock()

    def intentar(indice: int) -> None:
        propia = conectar(ruta_db)
        try:
            barrera.wait()
            resultado = service.reclamar_siguiente(propia, f"token-{indice:02d}-{'x' * 20}")
        finally:
            propia.close()
        with cerrojo:
            resultados.append(resultado)

    hilos = [threading.Thread(target=intentar, args=(i,)) for i in range(participantes)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join()

    ganadores = [resultado for resultado in resultados if resultado is not None]
    assert ganadores == [trabajo_id]
    verificacion = conectar(ruta_db)
    try:
        fila = verificacion.execute("SELECT estado, intentos FROM trabajos WHERE id = ?", (trabajo_id,)).fetchone()
        assert (fila["estado"], fila["intentos"]) == ("ejecutando", 1)
    finally:
        verificacion.close()


def test_nunca_hay_dos_trabajos_ejecutandose(conexion):
    for _ in range(3):
        service.crear(conexion, "diagnostico_espera", {})
    primero = service.reclamar_siguiente(conexion, "a" * 32)
    segundo = service.reclamar_siguiente(conexion, "b" * 32)
    assert primero is not None
    assert segundo is None
    ejecutando = conexion.execute("SELECT COUNT(*) FROM trabajos WHERE estado = 'ejecutando'").fetchone()[0]
    assert ejecutando == 1


def test_token_ajeno_no_puede_renovar_ni_completar(conexion):
    trabajo_id = service.crear(conexion, "diagnostico_espera", {})
    token = "t" * 32
    assert service.reclamar_siguiente(conexion, token) == trabajo_id

    with pytest.raises(ReclamoPerdido):
        service.latido(conexion, trabajo_id, "intruso")
    assert service.completar(conexion, trabajo_id, "intruso") is False
    assert service.fallar(conexion, trabajo_id, "intruso", "error") is False
    assert service.latido(conexion, trabajo_id, token) is False
    assert service.consultar(conexion, trabajo_id)["estado"] == "ejecutando"


def test_cancelar_en_cola_es_idempotente_y_impide_reclamo(conexion):
    trabajo_id = service.crear(conexion, "diagnostico_espera", {})
    primera = service.cancelar(conexion, trabajo_id)
    segunda = service.cancelar(conexion, trabajo_id)
    assert primera["estado"] == segunda["estado"] == "cancelado"
    assert service.reclamar_siguiente(conexion, "c" * 32) is None


def test_cancelacion_durante_ejecucion_bloquea_confirmaciones_tardias(conexion):
    trabajo_id = service.crear(conexion, "diagnostico_espera", {}, [("audio", 0, 0, 1000)])
    token = "d" * 32
    assert service.reclamar_siguiente(conexion, token) == trabajo_id
    assert service.marcar_segmento_procesando(conexion, trabajo_id, token, "audio", 0) is True

    respuesta = service.cancelar(conexion, trabajo_id)
    assert respuesta["estado"] == "ejecutando"
    assert respuesta["cancelacion_solicitada"] is True
    assert service.latido(conexion, trabajo_id, token) is True

    assert service.completar(conexion, trabajo_id, token) is False
    with pytest.raises(TrabajoCancelado):
        service.confirmar_segmento(conexion, trabajo_id, token, "audio", 0, "ruta.bin", 10, "1")

    assert service.cancelar_ejecucion(conexion, trabajo_id, token) is True
    final = service.consultar(conexion, trabajo_id)
    assert final["estado"] == "cancelado"
    segmento = conexion.execute(
        "SELECT estado FROM segmentos_trabajo WHERE trabajo_id = ? AND indice = 0", (trabajo_id,)
    ).fetchone()
    assert segmento["estado"] == "fallido"

    # Una confirmación posterior con el mismo token ya no tiene efecto.
    assert service.completar(conexion, trabajo_id, token) is False
    assert service.cancelar(conexion, trabajo_id)["estado"] == "cancelado"


def test_confirmacion_de_segmento_con_token_vigente(conexion):
    trabajo_id = service.crear(
        conexion,
        "diagnostico_espera",
        {},
        [("audio", 0, 0, 1000), ("video", 0, 0, 1000)],
    )
    token = "e" * 32
    assert service.reclamar_siguiente(conexion, token) == trabajo_id
    assert service.marcar_segmento_procesando(conexion, trabajo_id, token, "audio", 0) is True
    assert service.confirmar_segmento(conexion, trabajo_id, token, "audio", 0, None, None, "v1") is True

    video = conexion.execute(
        "SELECT estado FROM segmentos_trabajo WHERE trabajo_id = ? AND tipo_analisis = 'video'", (trabajo_id,)
    ).fetchone()
    assert video["estado"] == "pendiente"

    with pytest.raises(ReclamoPerdido):
        service.confirmar_segmento(conexion, trabajo_id, "otro", "video", 0, None, None, "v1")


def test_cerrar_tras_proceso_sin_confirmacion_falla(conexion):
    trabajo_id = service.crear(conexion, "diagnostico_espera", {})
    token = "f" * 32
    service.reclamar_siguiente(conexion, token)
    resultado = service.cerrar_tras_proceso(conexion, trabajo_id, token, 0, False, 3)
    assert resultado == "fallido"
    assert "sin confirmar el resultado" in service.consultar(conexion, trabajo_id)["error"]


def test_reencolar_interrumpido_respeta_el_limite_de_intentos(conexion):
    trabajo_id = service.crear(conexion, "diagnostico_espera", {})
    resultados = []
    for numero in range(3):
        token = f"{numero}" * 32
        assert service.reclamar_siguiente(conexion, token) == trabajo_id
        resultados.append(service.reencolar_interrumpido(conexion, trabajo_id, token, max_intentos=3))
    assert resultados == ["reencolado", "reencolado", "fallido"]
    assert service.consultar(conexion, trabajo_id)["estado"] == "fallido"


def test_reencolar_con_cancelacion_pasa_a_cancelado(conexion):
    trabajo_id = service.crear(conexion, "diagnostico_espera", {})
    token = "g" * 32
    service.reclamar_siguiente(conexion, token)
    service.cancelar(conexion, trabajo_id)
    assert service.reencolar_interrumpido(conexion, trabajo_id, token, max_intentos=3) == "cancelado"


@pytest.mark.parametrize(
    "texto,esperado_sin",
    [
        (r"No se pudo abrir C:\Users\inder\Videos\clip.mp4", r"C:\Users"),
        (r"Error en \\servidor\compartido\clip.mp4", r"servidor\compartido"),
        ("Error en /home/usuario/videos/clip.mp4 al leer", "/home/usuario"),
    ],
)
def test_mensaje_seguro_quita_rutas(texto, esperado_sin):
    limpio = service.mensaje_seguro(texto)
    assert esperado_sin not in limpio
    assert "<ruta>" in limpio


def test_mensaje_seguro_conserva_texto_sin_rutas():
    assert service.mensaje_seguro("1/2 de avance completado") == "1/2 de avance completado"


def test_mensaje_seguro_limita_longitud():
    assert len(service.mensaje_seguro("x" * 5000)) == service.LONGITUD_ERROR


def test_latido_vencido():
    assert service.latido_vencido(None, 60) is True
    assert service.latido_vencido("2020-01-01T00:00:00.000Z", 60) is True
    assert service.latido_vencido(service.ahora_iso(), 60) is False
