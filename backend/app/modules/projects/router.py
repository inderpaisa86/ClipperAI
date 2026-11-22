import sqlite3

from fastapi import APIRouter, Depends

from app.db.conexion import obtener_conexion
from app.modules.projects import service
from app.modules.projects.schemas import ProyectoCrear, ProyectoRespuesta

router = APIRouter(prefix="/proyectos", tags=["proyectos"])


@router.get("", response_model=list[ProyectoRespuesta])
def listar_proyectos(conexion: sqlite3.Connection = Depends(obtener_conexion)):
    return service.listar(conexion)


@router.post("", response_model=ProyectoRespuesta, status_code=201)
def crear_proyecto(
    datos: ProyectoCrear,
    conexion: sqlite3.Connection = Depends(obtener_conexion),
):
    return service.crear(conexion, datos)
