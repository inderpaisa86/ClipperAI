import sqlite3
from collections.abc import Iterator
from pathlib import Path as RutaArchivo

from fastapi import APIRouter, Depends, Path, Query, Request
from fastapi.responses import StreamingResponse

from app.core.rutas import RaizDatos
from app.db.conexion import obtener_conexion
from app.modules.analisis import service
from app.modules.analisis.schemas import (
    AnalisisRespuesta,
    FotogramaRespuesta,
    InicioAnalisisRespuesta,
    SenalRespuesta,
)
from app.plugins.contrato import PATRON_IDENTIFICADOR

router = APIRouter(prefix="/videos/{video_id}/analisis", tags=["analisis"])

PATRON_ANALIZADOR = PATRON_IDENTIFICADOR.pattern
TAMANO_BLOQUE_IMAGEN = 64 * 1024


@router.post("", status_code=202, response_model=list[InicioAnalisisRespuesta])
def iniciar_analisis(
    request: Request,
    video_id: int = Path(gt=0),
    conexion: sqlite3.Connection = Depends(obtener_conexion),
):
    """Inicia los analizadores registrados para el video. Responde 202 con el trabajo y el estado de cada uno.

    No repite análisis completos ni duplica trabajos activos. Reintenta los fallidos o cancelados.
    """
    return service.iniciar(conexion, video_id, request.app.state.lanzadores)


@router.get("", response_model=list[AnalisisRespuesta])
def listar_analisis(
    video_id: int = Path(gt=0),
    conexion: sqlite3.Connection = Depends(obtener_conexion),
):
    return service.listar_analisis(conexion, video_id)


@router.get("/{analizador}", response_model=AnalisisRespuesta)
def obtener_analisis(
    video_id: int = Path(gt=0),
    analizador: str = Path(pattern=PATRON_ANALIZADOR),
    conexion: sqlite3.Connection = Depends(obtener_conexion),
):
    return service.obtener_analisis(conexion, video_id, analizador)


@router.get("/{analizador}/senales", response_model=list[SenalRespuesta])
def listar_senales(
    video_id: int = Path(gt=0),
    analizador: str = Path(pattern=PATRON_ANALIZADOR),
    inicio_ms: int | None = Query(default=None, ge=0),
    fin_ms: int | None = Query(default=None, ge=0),
    limite: int = Query(default=service.LIMITE_CONSULTA_POR_DEFECTO, ge=1, le=service.LIMITE_MAXIMO_CONSULTA),
    tipo: str | None = Query(default=None, max_length=32),
    conexion: sqlite3.Connection = Depends(obtener_conexion),
):
    """Señales que se solapan con [inicio_ms, fin_ms]. Los tiempos son milisegundos.

    `tipo` filtra por un tipo del vocabulario cerrado; un valor fuera de él responde 422.
    """
    return service.listar_senales(conexion, video_id, analizador, inicio_ms, fin_ms, limite, tipo)


@router.get("/{analizador}/fotogramas", response_model=list[FotogramaRespuesta])
def listar_fotogramas(
    video_id: int = Path(gt=0),
    analizador: str = Path(pattern=PATRON_ANALIZADOR),
    limite: int = Query(default=service.LIMITE_CONSULTA_POR_DEFECTO, ge=1, le=service.LIMITE_MAXIMO_CONSULTA),
    conexion: sqlite3.Connection = Depends(obtener_conexion),
):
    return service.listar_fotogramas(conexion, video_id, analizador, limite)


@router.get("/{analizador}/fotogramas/{tiempo_ms}/miniatura")
def obtener_miniatura(
    request: Request,
    video_id: int = Path(gt=0),
    analizador: str = Path(pattern=PATRON_ANALIZADOR),
    tiempo_ms: int = Path(ge=0),
    conexion: sqlite3.Connection = Depends(obtener_conexion),
):
    """Miniatura JPEG. Se lee en bloques y la ruta en disco nunca aparece en la respuesta."""
    raiz = RaizDatos(request.app.state.configuracion.data_dir)
    ruta = service.ruta_miniatura(conexion, raiz, video_id, analizador, tiempo_ms)
    tamano = ruta.stat().st_size
    return StreamingResponse(
        _leer_en_bloques(ruta),
        media_type="image/jpeg",
        headers={"Cache-Control": "no-store", "Content-Length": str(tamano)},
    )


def _leer_en_bloques(ruta: RutaArchivo) -> Iterator[bytes]:
    with open(ruta, "rb") as archivo:
        while bloque := archivo.read(TAMANO_BLOQUE_IMAGEN):
            yield bloque
