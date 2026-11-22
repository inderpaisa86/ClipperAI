import sqlite3

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import StreamingResponse

from app.core.dialogo_archivos import seleccionar_video
from app.core.plataforma import detectar_plataforma
from app.db.conexion import obtener_conexion
from app.modules.videos import service
from app.modules.videos.schemas import SeleccionRespuesta, VideoCrear, VideoRespuesta
from app.modules.videos.streaming import RangoNoSatisfacible, interpretar_rango, iterar_archivo

router = APIRouter(prefix="/videos", tags=["videos"])


@router.get("", response_model=list[VideoRespuesta])
def listar_videos(
    proyecto_id: int = Query(gt=0),
    conexion: sqlite3.Connection = Depends(obtener_conexion),
):
    return service.listar(conexion, proyecto_id)


@router.post("", response_model=VideoRespuesta, status_code=201)
def importar_video(
    datos: VideoCrear,
    request: Request,
    conexion: sqlite3.Connection = Depends(obtener_conexion),
):
    configuracion = request.app.state.configuracion
    return service.importar(
        conexion,
        datos,
        configuracion.ffprobe,
        detectar_plataforma().sistema,
    )


@router.post("/seleccion", response_model=SeleccionRespuesta)
def seleccionar_archivo():
    """Abre el selector nativo del sistema. Responde con la ruta elegida o null si se cancela."""
    ruta = seleccionar_video(detectar_plataforma().sistema)
    return SeleccionRespuesta(ruta=str(ruta) if ruta is not None else None)


@router.get("/{video_id}", response_model=VideoRespuesta)
def obtener_video(
    video_id: int,
    conexion: sqlite3.Connection = Depends(obtener_conexion),
):
    return service.obtener(conexion, video_id)


@router.delete("/{video_id}", status_code=204)
def eliminar_video(
    video_id: int,
    conexion: sqlite3.Connection = Depends(obtener_conexion),
):
    """Elimina solo el registro. El archivo original permanece intacto."""
    service.eliminar(conexion, video_id)
    return Response(status_code=204)


@router.get("/{video_id}/stream")
def transmitir_video(
    video_id: int,
    request: Request,
    conexion: sqlite3.Connection = Depends(obtener_conexion),
):
    ruta, tipo = service.ruta_para_transmision(conexion, video_id)
    tamano = ruta.stat().st_size

    try:
        rango = interpretar_rango(request.headers.get("range"), tamano)
    except RangoNoSatisfacible:
        return Response(
            status_code=416,
            headers={"Content-Range": f"bytes */{tamano}", "Accept-Ranges": "bytes"},
        )

    cabeceras = {"Accept-Ranges": "bytes", "Cache-Control": "no-store"}
    if rango is None:
        inicio, fin, estado = 0, tamano - 1, 200
    else:
        inicio, fin, estado = rango.inicio, rango.fin, 206
        cabeceras["Content-Range"] = f"bytes {inicio}-{fin}/{tamano}"
    cabeceras["Content-Length"] = str(max(fin - inicio + 1, 0))

    return StreamingResponse(
        iterar_archivo(ruta, inicio, fin),
        status_code=estado,
        media_type=tipo,
        headers=cabeceras,
    )

