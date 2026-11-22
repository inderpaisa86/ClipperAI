import sqlite3
import threading
from types import SimpleNamespace

import pytest

from app.db.conexion import obtener_conexion


def _peticion(configuracion):
    """Imita el objeto Request de FastAPI. La dependencia solo lee request.app.state.configuracion."""
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(configuracion=configuracion)))


def _en_hilo(funcion):
    """Ejecuta funcion en otro hilo y devuelve la excepción que lance, o None."""
    error = {}

    def envoltorio():
        try:
            funcion()
        except BaseException as excepcion:  # noqa: BLE001 - se devuelve al hilo de la prueba
            error["excepcion"] = excepcion

    hilo = threading.Thread(target=envoltorio)
    hilo.start()
    hilo.join()
    return error.get("excepcion")


def test_cierre_en_otro_hilo_no_falla(configuracion):
    """FastAPI puede crear y cerrar la dependencia en hilos distintos del pool.
    Reproduce el 500 de SQLite: 'objects created in a thread can only be used in that same thread'.
    """
    generador = obtener_conexion(_peticion(configuracion))
    conexion = next(generador)

    def terminar_dependencia():
        with pytest.raises(StopIteration):
            next(generador)

    assert _en_hilo(terminar_dependencia) is None


def test_conexion_se_puede_usar_en_otro_hilo_y_queda_cerrada(configuracion):
    generador = obtener_conexion(_peticion(configuracion))
    conexion = next(generador)

    resultado = {}

    def consultar():
        resultado["valor"] = conexion.execute("SELECT 1").fetchone()[0]

    assert _en_hilo(consultar) is None
    assert resultado["valor"] == 1

    assert _en_hilo(lambda: next(generador, None)) is None

    with pytest.raises(sqlite3.ProgrammingError):
        conexion.execute("SELECT 1")


def test_error_del_endpoint_igualmente_cierra_la_conexion(configuracion):
    generador = obtener_conexion(_peticion(configuracion))
    conexion = next(generador)

    with pytest.raises(RuntimeError, match="fallo simulado"):
        generador.throw(RuntimeError("fallo simulado"))

    with pytest.raises(sqlite3.ProgrammingError):
        conexion.execute("SELECT 1")


def test_endpoints_con_dependencia_responden_repetidamente(cliente):
    """Regresión: varias peticiones seguidas a endpoints que usan la dependencia responden 200."""
    for _ in range(25):
        assert cliente.get("/api/v1/proyectos").status_code == 200
        assert cliente.get("/api/v1/salud").status_code == 200
