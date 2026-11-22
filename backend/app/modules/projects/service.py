import sqlite3

from app.core.errores import NoEncontrado
from app.modules.projects import repository
from app.modules.projects.schemas import ProyectoCrear, ProyectoRespuesta
from app.modules.videos import service as videos


def _a_respuesta(fila: sqlite3.Row, cantidad_videos: int) -> ProyectoRespuesta:
    return ProyectoRespuesta(
        id=fila["id"],
        nombre=fila["nombre"],
        creado=fila["creado"],
        cantidad_videos=cantidad_videos,
    )


def crear(conexion: sqlite3.Connection, datos: ProyectoCrear) -> ProyectoRespuesta:
    proyecto_id = repository.insertar(conexion, datos.nombre)
    return obtener(conexion, proyecto_id)


def listar(conexion: sqlite3.Connection) -> list[ProyectoRespuesta]:
    # El conteo sale del servicio de videos. Este módulo no lee la tabla videos.
    cantidades = videos.contar_por_proyectos(conexion)
    return [
        _a_respuesta(fila, cantidades.get(fila["id"], 0))
        for fila in repository.listar(conexion)
    ]


def obtener(conexion: sqlite3.Connection, proyecto_id: int) -> ProyectoRespuesta:
    fila = repository.obtener(conexion, proyecto_id)
    if fila is None:
        raise NoEncontrado("El proyecto no existe.")
    cantidad = videos.contar_por_proyecto(conexion, proyecto_id)
    return _a_respuesta(fila, cantidad)
