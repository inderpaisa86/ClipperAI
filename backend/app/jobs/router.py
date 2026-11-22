import sqlite3

from fastapi import APIRouter, Depends, Path

from app.db.conexion import obtener_conexion
from app.jobs import service
from app.jobs.schemas import TrabajoRespuesta

router = APIRouter(prefix="/jobs", tags=["trabajos"])


@router.get("/{trabajo_id}", response_model=TrabajoRespuesta)
def consultar_trabajo(
    trabajo_id: int = Path(gt=0),
    conexion: sqlite3.Connection = Depends(obtener_conexion),
):
    return service.consultar(conexion, trabajo_id)


@router.post("/{trabajo_id}/cancelacion", response_model=TrabajoRespuesta, status_code=202)
def cancelar_trabajo(
    trabajo_id: int = Path(gt=0),
    conexion: sqlite3.Connection = Depends(obtener_conexion),
):
    """Cancelación idempotente. Repetirla no cambia el resultado."""
    return service.cancelar(conexion, trabajo_id)
