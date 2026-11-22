import sqlite3

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.core.herramientas import diagnosticar_herramienta
from app.core.plataforma import detectar_plataforma
from app.db.conexion import conectar

router = APIRouter(tags=["sistema"])


class PlataformaRespuesta(BaseModel):
    sistema: str
    arquitectura: str
    cpus_logicas: int
    apple_silicon: bool


class HerramientaRespuesta(BaseModel):
    disponible: bool
    version: str | None
    mensaje: str | None


class SaludRespuesta(BaseModel):
    estado: str
    plataforma: PlataformaRespuesta
    ffmpeg: HerramientaRespuesta
    ffprobe: HerramientaRespuesta
    base_datos: str


def _estado_base_datos(ruta) -> str:
    try:
        conexion = conectar(ruta)
        try:
            conexion.execute("SELECT 1").fetchone()
        finally:
            conexion.close()
    except sqlite3.Error:
        return "error"
    return "ok"


@router.get("/salud", response_model=SaludRespuesta)
def salud(request: Request) -> SaludRespuesta:
    configuracion = request.app.state.configuracion
    info = detectar_plataforma()
    ffmpeg = diagnosticar_herramienta("ffmpeg", configuracion.ffmpeg, info.sistema)
    ffprobe = diagnosticar_herramienta("ffprobe", configuracion.ffprobe, info.sistema)
    base_datos = _estado_base_datos(configuracion.ruta_base_datos)

    herramientas_ok = ffmpeg.disponible and ffprobe.disponible
    estado = "ok" if herramientas_ok and base_datos == "ok" else "degradado"

    return SaludRespuesta(
        estado=estado,
        plataforma=PlataformaRespuesta(
            sistema=info.sistema,
            arquitectura=info.arquitectura,
            cpus_logicas=info.cpus_logicas,
            apple_silicon=info.es_apple_silicon,
        ),
        ffmpeg=HerramientaRespuesta(**vars(ffmpeg)),
        ffprobe=HerramientaRespuesta(**vars(ffprobe)),
        base_datos=base_datos,
    )
