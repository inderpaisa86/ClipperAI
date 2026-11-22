from fastapi.testclient import TestClient

from app.core.configuracion import Configuracion
from app.db.conexion import conectar
from app.jobs import service
from app.main import ENCABEZADO_TOKEN, crear_aplicacion


def _crear_trabajo(configuracion: Configuracion) -> int:
    conexion = conectar(configuracion.ruta_base_datos)
    try:
        return service.crear(conexion, "diagnostico_espera", {"segundos": 1})
    finally:
        conexion.close()


def test_consultar_trabajo_devuelve_solo_campos_publicos(configuracion: Configuracion):
    aplicacion = crear_aplicacion(configuracion)
    with TestClient(aplicacion, base_url="http://127.0.0.1:8000") as cliente:
        cliente.headers[ENCABEZADO_TOKEN] = aplicacion.state.token
        trabajo_id = _crear_trabajo(configuracion)

        respuesta = cliente.get(f"/api/v1/jobs/{trabajo_id}")

        assert respuesta.status_code == 200
        cuerpo = respuesta.json()
        assert cuerpo["estado"] == "en_cola"
        assert set(cuerpo) == {
            "id", "tipo", "estado", "progreso", "cancelacion_solicitada",
            "intentos", "error", "creado", "actualizado",
        }


def test_trabajo_inexistente_responde_404(configuracion: Configuracion):
    aplicacion = crear_aplicacion(configuracion)
    with TestClient(aplicacion, base_url="http://127.0.0.1:8000") as cliente:
        cliente.headers[ENCABEZADO_TOKEN] = aplicacion.state.token
        assert cliente.get("/api/v1/jobs/999").status_code == 404


def test_identificador_invalido_responde_422(configuracion: Configuracion):
    aplicacion = crear_aplicacion(configuracion)
    with TestClient(aplicacion, base_url="http://127.0.0.1:8000") as cliente:
        cliente.headers[ENCABEZADO_TOKEN] = aplicacion.state.token
        assert cliente.get("/api/v1/jobs/abc").status_code == 422
        assert cliente.get("/api/v1/jobs/0").status_code == 422


def test_cancelacion_es_idempotente(configuracion: Configuracion):
    aplicacion = crear_aplicacion(configuracion)
    with TestClient(aplicacion, base_url="http://127.0.0.1:8000") as cliente:
        cliente.headers[ENCABEZADO_TOKEN] = aplicacion.state.token
        trabajo_id = _crear_trabajo(configuracion)

        primera = cliente.post(f"/api/v1/jobs/{trabajo_id}/cancelacion")
        segunda = cliente.post(f"/api/v1/jobs/{trabajo_id}/cancelacion")

        assert primera.status_code == segunda.status_code == 202
        assert primera.json()["estado"] == segunda.json()["estado"] == "cancelado"


def test_cancelar_trabajo_inexistente_responde_404(configuracion: Configuracion):
    aplicacion = crear_aplicacion(configuracion)
    with TestClient(aplicacion, base_url="http://127.0.0.1:8000") as cliente:
        cliente.headers[ENCABEZADO_TOKEN] = aplicacion.state.token
        assert cliente.post("/api/v1/jobs/999/cancelacion").status_code == 404


def test_no_existe_creacion_de_trabajos_por_api(configuracion: Configuracion):
    aplicacion = crear_aplicacion(configuracion)
    with TestClient(aplicacion, base_url="http://127.0.0.1:8000") as cliente:
        cliente.headers[ENCABEZADO_TOKEN] = aplicacion.state.token
        # Ninguna ruta POST /api/v1/jobs: la creación de trabajos queda solo en el código del servidor.
        respuesta = cliente.post("/api/v1/jobs", json={"tipo": "diagnostico_espera"})
        assert respuesta.status_code == 404


def test_trabajos_exigen_token(configuracion: Configuracion):
    aplicacion = crear_aplicacion(configuracion)
    with TestClient(aplicacion, base_url="http://127.0.0.1:8000") as cliente:
        trabajo_id = _crear_trabajo(configuracion)
        assert cliente.get(f"/api/v1/jobs/{trabajo_id}").status_code == 401
        assert cliente.post(f"/api/v1/jobs/{trabajo_id}/cancelacion").status_code == 401
