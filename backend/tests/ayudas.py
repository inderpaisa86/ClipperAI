from pathlib import Path


def crear_proyecto(cliente, nombre: str = "Proyecto de prueba") -> int:
    respuesta = cliente.post("/api/v1/proyectos", json={"nombre": nombre})
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()["id"]


def importar_video(cliente, proyecto_id: int, ruta: Path | str):
    return cliente.post("/api/v1/videos", json={"proyecto_id": proyecto_id, "ruta": str(ruta)})
