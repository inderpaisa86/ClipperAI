import sqlite3

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import StreamingResponse

from app.core.dialogo_archivos import seleccionar_video
from app.core.errores import SolicitudInvalida
from app.core.plataforma import detectar_plataforma
from app.core.rutas import RaizDatos
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
    """Registra un video por su ruta escrita o por una selección previa del selector nativo."""
    configuracion = request.app.state.configuracion
    if datos.seleccion_id is not None:
        ruta_elegida = request.app.state.selecciones.tomar(datos.seleccion_id)
        if ruta_elegida is None:
            raise SolicitudInvalida("La selección caducó o ya se usó. Seleccione el archivo de nuevo.")
        texto_ruta = str(ruta_elegida)
    else:
        texto_ruta = datos.ruta or ""
    return service.importar(
        conexion,
        datos.proyecto_id,
        texto_ruta,
        configuracion.ffprobe,
        detectar_plataforma().sistema,
    )


@router.post("/seleccion", response_model=SeleccionRespuesta)
def seleccionar_archivo(request: Request):
    """Abre el selector nativo. La ruta se guarda en el backend y el navegador recibe solo un identificador."""
    ruta = seleccionar_video(detectar_plataforma().sistema)
    if ruta is None:
        return SeleccionRespuesta(seleccion_id=None, nombre_archivo=None)
    identificador = request.app.state.selecciones.guardar(ruta)
    return SeleccionRespuesta(seleccion_id=identificador, nombre_archivo=ruta.name)


@router.get("/{video_id}", response_model=VideoRespuesta)
def obtener_video(
    video_id: int,
    conexion: sqlite3.Connection = Depends(obtener_conexion),
):
    return service.obtener(conexion, video_id)


@router.delete("/{video_id}", status_code=204)
def eliminar_video(
    video_id: int,
    request: Request,
    conexion: sqlite3.Connection = Depends(obtener_conexion),
):
    """Elimina el registro, sus análisis y sus miniaturas. El archivo original permanece intacto."""
    raiz = RaizDatos(request.app.state.configuracion.data_dir)
    service.eliminar(conexion, raiz, video_id)
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
