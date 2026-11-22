from tests.ayudas import crear_proyecto, importar_video
from tests.conftest import requiere_ffmpeg


def _cantidad_en_listado(cliente, proyecto_id: int) -> int:
    proyectos = cliente.get("/api/v1/proyectos").json()
    return next(p["cantidad_videos"] for p in proyectos if p["id"] == proyecto_id)


def test_proyecto_sin_videos_tiene_cantidad_cero(cliente):
    proyecto_id = crear_proyecto(cliente)
    respuesta = cliente.get("/api/v1/proyectos")
    assert respuesta.json()[0]["id"] == proyecto_id
    assert respuesta.json()[0]["cantidad_videos"] == 0


def test_creacion_devuelve_cantidad_cero(cliente):
    respuesta = cliente.post("/api/v1/proyectos", json={"nombre": "Nuevo"})
    assert respuesta.status_code == 201
    assert respuesta.json()["cantidad_videos"] == 0


@requiere_ffmpeg
def test_proyecto_con_un_video_cuenta_uno(cliente, generar_video):
    proyecto_id = crear_proyecto(cliente)
    assert importar_video(cliente, proyecto_id, generar_video("uno.mp4")).status_code == 201
    assert _cantidad_en_listado(cliente, proyecto_id) == 1


@requiere_ffmpeg
def test_proyecto_con_varios_videos_cuenta_todos(cliente, generar_video):
    proyecto_id = crear_proyecto(cliente)
    for nombre in ("a.mp4", "b.mp4", "c.mp4"):
        assert importar_video(cliente, proyecto_id, generar_video(nombre)).status_code == 201
    assert _cantidad_en_listado(cliente, proyecto_id) == 3


@requiere_ffmpeg
def test_cantidad_no_mezcla_videos_de_otros_proyectos(cliente, generar_video):
    con_videos = crear_proyecto(cliente, "Con videos")
    vacio = crear_proyecto(cliente, "Vacío")
    importar_video(cliente, con_videos, generar_video("x.mp4"))
    importar_video(cliente, con_videos, generar_video("y.mp4"))
    assert _cantidad_en_listado(cliente, con_videos) == 2
    assert _cantidad_en_listado(cliente, vacio) == 0


@requiere_ffmpeg
def test_detalle_de_proyecto_refleja_la_cantidad(cliente, generar_video):
    proyecto_id = crear_proyecto(cliente)
    video = importar_video(cliente, proyecto_id, generar_video("solo.mp4")).json()
    assert cliente.get("/api/v1/proyectos").json()[0]["cantidad_videos"] == 1
    cliente.delete(f"/api/v1/videos/{video['id']}")
    assert _cantidad_en_listado(cliente, proyecto_id) == 0


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
