from pathlib import Path

import pytest

from app.db.conexion import conectar
from app.db.migraciones import aplicar_migraciones
from app.jobs import service
from app.jobs.service import ReclamoPerdido


@pytest.fixture
def conexion(tmp_path: Path):
    conexion = conectar(tmp_path / "datos" / "clipperai.db")
    aplicar_migraciones(conexion)
    yield conexion
    conexion.close()


def _intentos(conexion, trabajo_id: int) -> int:
    return conexion.execute("SELECT intentos FROM trabajos WHERE id = ?", (trabajo_id,)).fetchone()[0]


def _token_de_la_fila(conexion, trabajo_id: int) -> str | None:
    return conexion.execute("SELECT claim_token FROM trabajos WHERE id = ?", (trabajo_id,)).fetchone()[0]


def _afirmar_token_invalidado(conexion, trabajo_id: int, token_anterior: str) -> None:
    with pytest.raises(ReclamoPerdido):
        service.latido(conexion, trabajo_id, token_anterior)
    assert service.completar(conexion, trabajo_id, token_anterior) is False
    assert service.fallar(conexion, trabajo_id, token_anterior, "tardío") is False
    with pytest.raises(ReclamoPerdido):
        service.confirmar_segmento(conexion, trabajo_id, token_anterior, "audio", 0, None, None, "v1")
    with pytest.raises(ReclamoPerdido):
        service.marcar_segmento_procesando(conexion, trabajo_id, token_anterior, "audio", 0)


def test_parada_ordenada_no_consume_intentos(conexion):
    trabajo_id = service.crear(conexion, "diagnostico_espera", {}, [("audio", 0, 0, 1000)])
    token = "a" * 32
    assert service.reclamar_siguiente(conexion, token) == trabajo_id
    assert service.marcar_segmento_procesando(conexion, trabajo_id, token, "audio", 0) is True
    assert _intentos(conexion, trabajo_id) == 1

    # max_intentos=1 deja claro que la parada no se evalúa contra el límite.
    resultado = service.cerrar_tras_proceso(conexion, trabajo_id, token, None, "parada")

    assert resultado == "reencolado"
    respuesta = service.consultar(conexion, trabajo_id)
    assert respuesta["estado"] == "en_cola"
    assert respuesta["intentos"] == 0
    assert respuesta["error"] is None
    assert _token_de_la_fila(conexion, trabajo_id) is None
    segmento = conexion.execute(
        "SELECT estado FROM segmentos_trabajo WHERE trabajo_id = ?", (trabajo_id,)
    ).fetchone()
    assert segmento["estado"] == "pendiente"


def test_token_anterior_no_puede_confirmar_tras_parada(conexion):
    trabajo_id = service.crear(conexion, "diagnostico_espera", {}, [("audio", 0, 0, 1000)])
    token_anterior = "b" * 32
    service.reclamar_siguiente(conexion, token_anterior)
    service.marcar_segmento_procesando(conexion, trabajo_id, token_anterior, "audio", 0)
    service.cerrar_tras_proceso(conexion, trabajo_id, token_anterior, None, "parada")

    _afirmar_token_invalidado(conexion, trabajo_id, token_anterior)

    # El estado no cambió por los intentos fallidos del proceso anterior.
    respuesta = service.consultar(conexion, trabajo_id)
    assert respuesta["estado"] == "en_cola"
    assert respuesta["intentos"] == 0


def test_reasignacion_usa_token_nuevo_y_cuenta_un_solo_intento(conexion):
    trabajo_id = service.crear(conexion, "diagnostico_espera", {})
    token_anterior = "c" * 32
    token_nuevo = "d" * 32
    service.reclamar_siguiente(conexion, token_anterior)
    service.cerrar_tras_proceso(conexion, trabajo_id, token_anterior, None, "parada")

    assert service.reclamar_siguiente(conexion, token_nuevo) == trabajo_id
    assert _intentos(conexion, trabajo_id) == 1
    assert service.latido(conexion, trabajo_id, token_nuevo) is False
    _afirmar_token_invalidado(conexion, trabajo_id, token_anterior)


def test_paradas_repetidas_no_acumulan_intentos(conexion):
    trabajo_id = service.crear(conexion, "diagnostico_espera", {})
    for numero in range(4):
        token = f"{numero}" * 32
        assert service.reclamar_siguiente(conexion, token) == trabajo_id
        assert service.cerrar_tras_proceso(conexion, trabajo_id, token, None, "parada") == "reencolado"
    assert service.consultar(conexion, trabajo_id)["intentos"] == 0
    assert service.consultar(conexion, trabajo_id)["estado"] == "en_cola"


def test_parada_con_cancelacion_pendiente_cancela(conexion):
    trabajo_id = service.crear(conexion, "diagnostico_espera", {})
    token = "e" * 32
    service.reclamar_siguiente(conexion, token)
    service.cancelar(conexion, trabajo_id)

    assert service.cerrar_tras_proceso(conexion, trabajo_id, token, None, "parada") == "cancelado"
    assert service.consultar(conexion, trabajo_id)["estado"] == "cancelado"


def test_fallo_real_consume_el_intento(conexion):
    trabajo_id = service.crear(conexion, "diagnostico_fallo", {})
    token = "f" * 32
    service.reclamar_siguiente(conexion, token)

    assert service.fallar(conexion, trabajo_id, token, "Fallo controlado") is True

    respuesta = service.consultar(conexion, trabajo_id)
    assert respuesta["estado"] == "fallido"
    assert respuesta["intentos"] == 1
    assert service.reclamar_siguiente(conexion, "9" * 32) is None


def test_proceso_sin_confirmacion_consume_el_intento(conexion):
    trabajo_id = service.crear(conexion, "diagnostico_espera", {})
    token = "7" * 32
    service.reclamar_siguiente(conexion, token)

    assert service.cerrar_tras_proceso(conexion, trabajo_id, token, 0, "salida") == "fallido"
    assert service.consultar(conexion, trabajo_id)["intentos"] == 1


def test_recuperacion_de_proceso_muerto_conserva_el_intento(conexion):
    trabajo_id = service.crear(conexion, "diagnostico_espera", {})
    token = "6" * 32
    service.reclamar_siguiente(conexion, token)

    assert service.reencolar_interrumpido(conexion, trabajo_id, token, max_intentos=3) == "reencolado"

    respuesta = service.consultar(conexion, trabajo_id)
    assert respuesta["estado"] == "en_cola"
    assert respuesta["intentos"] == 1
    _afirmar_token_invalidado(conexion, trabajo_id, token)
