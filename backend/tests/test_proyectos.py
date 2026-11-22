from tests.ayudas import crear_proyecto


def test_crea_y_lista_proyectos(cliente):
    proyecto_id = crear_proyecto(cliente, "Podcast semanal")

    respuesta = cliente.get("/api/v1/proyectos")

    assert respuesta.status_code == 200
    proyectos = respuesta.json()
    assert [p["id"] for p in proyectos] == [proyecto_id]
    assert proyectos[0]["nombre"] == "Podcast semanal"
    assert proyectos[0]["creado"]


def test_recorta_espacios_del_nombre(cliente):
    respuesta = cliente.post("/api/v1/proyectos", json={"nombre": "   Entrevistas   "})

    assert respuesta.status_code == 201
    assert respuesta.json()["nombre"] == "Entrevistas"


def test_rechaza_nombre_vacio(cliente):
    respuesta = cliente.post("/api/v1/proyectos", json={"nombre": "   "})

    assert respuesta.status_code == 422
    assert "detalle" in respuesta.json()


def test_rechaza_nombre_demasiado_largo(cliente):
    respuesta = cliente.post("/api/v1/proyectos", json={"nombre": "x" * 121})

    assert respuesta.status_code == 422
