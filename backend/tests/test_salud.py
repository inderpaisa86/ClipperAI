import pytest
from fastapi.testclient import TestClient

from app.core.configuracion import Configuracion
from app.main import ENCABEZADO_TOKEN, crear_aplicacion


@pytest.fixture
def cliente(tmp_path):
    aplicacion = crear_aplicacion(Configuracion(data_dir=tmp_path / "datos"))
    with TestClient(aplicacion, base_url="http://127.0.0.1:8000") as cliente_http:
        yield cliente_http, aplicacion.state.token


def test_salud_rechaza_peticion_sin_token(cliente):
    http, _ = cliente

    respuesta = http.get("/api/v1/salud")

    assert respuesta.status_code == 401


def test_salud_acepta_token_valido(cliente):
    http, token = cliente

    respuesta = http.get("/api/v1/salud", headers={ENCABEZADO_TOKEN: token})

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["base_datos"] == "ok"
    assert cuerpo["plataforma"]["sistema"] in {"windows", "macos", "linux", "desconocido"}


def test_rechaza_host_no_permitido(cliente):
    http, token = cliente

    respuesta = http.get(
        "/api/v1/salud",
        headers={ENCABEZADO_TOKEN: token, "host": "evil.example"},
    )

    assert respuesta.status_code == 403


def test_rechaza_origen_no_permitido(cliente):
    http, token = cliente

    respuesta = http.get(
        "/api/v1/salud",
        headers={ENCABEZADO_TOKEN: token, "origin": "http://evil.example"},
    )

    assert respuesta.status_code == 403


def test_acepta_origen_del_frontend(cliente):
    http, token = cliente

    respuesta = http.get(
        "/api/v1/salud",
        headers={ENCABEZADO_TOKEN: token, "origin": "http://localhost:3000"},
    )

    assert respuesta.status_code == 200


def test_token_se_elimina_al_cerrar(tmp_path):
    configuracion = Configuracion(data_dir=tmp_path / "datos")
    aplicacion = crear_aplicacion(configuracion)

    with TestClient(aplicacion, base_url="http://127.0.0.1:8000"):
        assert configuracion.ruta_token.exists()

    assert not configuracion.ruta_token.exists()
