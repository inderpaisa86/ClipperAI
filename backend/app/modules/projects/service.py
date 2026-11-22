import sqlite3

from app.core.errores import NoEncontrado
from app.modules.projects import repository
from app.modules.projects.schemas import ProyectoCrear, ProyectoRespuesta


def _a_respuesta(fila: sqlite3.Row) -> ProyectoRespuesta:
    return ProyectoRespuesta(id=fila["id"], nombre=fila["nombre"], creado=fila["creado"])


def crear(conexion: sqlite3.Connection, datos: ProyectoCrear) -> ProyectoRespuesta:
    proyecto_id = repository.insertar(conexion, datos.nombre)
    return obtener(conexion, proyecto_id)


def listar(conexion: sqlite3.Connection) -> list[ProyectoRespuesta]:
    return [_a_respuesta(fila) for fila in repository.listar(conexion)]


def obtener(conexion: sqlite3.Connection, proyecto_id: int) -> ProyectoRespuesta:
    fila = repository.obtener(conexion, proyecto_id)
    if fila is None:
        raise NoEncontrado("El proyecto no existe.")
    return _a_respuesta(fila)
