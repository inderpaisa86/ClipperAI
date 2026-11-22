import sqlite3
import stat
from pathlib import Path

from app.core.errores import Conflicto, NoEncontrado, SolicitudInvalida
from app.modules.projects import service as proyectos
from app.modules.videos import repository
from app.modules.videos.ffprobe import leer_metadatos
from app.modules.videos.schemas import VideoCrear, VideoRespuesta

LONGITUD_MAXIMA_RUTA = 4096

# Formatos contenedores admitidos. FFprobe valida después que el archivo sea realmente legible.
EXTENSIONES_ADMITIDAS: dict[str, str] = {
    ".mp4": "video/mp4",
    ".m4v": "video/mp4",
    ".mov": "video/quicktime",
    ".mkv": "video/x-matroska",
    ".webm": "video/webm",
    ".avi": "video/x-msvideo",
}


def validar_ruta_entrada(texto: str) -> Path:
    """Valida una ruta escrita por el usuario o devuelta por el selector nativo.

    Exige una ruta absoluta, un archivo regular (no enlace simbólico), extensión admitida,
    tamaño mayor que cero y permiso de lectura. Las rutas pueden contener espacios, tildes
    y otros caracteres, porque se usan como cadenas de Path y nunca en un shell.
    """
    limpia = texto.strip()
    if not limpia:
        raise SolicitudInvalida("Indique la ruta del video.")
    if len(limpia) > LONGITUD_MAXIMA_RUTA:
        raise SolicitudInvalida("La ruta es demasiado larga.")
    if "\x00" in limpia:
        raise SolicitudInvalida("La ruta contiene caracteres no válidos.")

    ruta = Path(limpia)
    if not ruta.is_absolute():
        raise SolicitudInvalida("La ruta debe ser absoluta.")

    extension = ruta.suffix.lower()
    if extension not in EXTENSIONES_ADMITIDAS:
        admitidas = ", ".join(sorted(EXTENSIONES_ADMITIDAS))
        raise SolicitudInvalida(f"Formato no compatible. Formatos admitidos: {admitidas}.")

    try:
        estado = ruta.lstat()
    except FileNotFoundError as error:
        raise SolicitudInvalida("El archivo no existe.") from error
    except OSError as error:
        raise SolicitudInvalida("No se puede acceder al archivo.") from error

    if stat.S_ISLNK(estado.st_mode):
        raise SolicitudInvalida(
            "No se admiten enlaces simbólicos. Seleccione el archivo original."
        )
    if not stat.S_ISREG(estado.st_mode):
        raise SolicitudInvalida("La ruta no corresponde a un archivo.")
    if estado.st_size == 0:
        raise SolicitudInvalida("El archivo está vacío.")

    try:
        with open(ruta, "rb"):
            pass
    except OSError as error:
        raise SolicitudInvalida("No hay permiso para leer el archivo.") from error

    return ruta


def _a_respuesta(fila: sqlite3.Row) -> VideoRespuesta:
    return VideoRespuesta(
        id=fila["id"],
        proyecto_id=fila["proyecto_id"],
        nombre=fila["nombre"],
        ruta=fila["ruta_original"],
        tamano_bytes=fila["tamano_bytes"],
        duracion_segundos=fila["duracion_segundos"],
        ancho=fila["ancho"],
        alto=fila["alto"],
        fps=fila["fps"],
        codec_video=fila["codec_video"],
        codec_audio=fila["codec_audio"],
        formato=fila["formato"],
        disponible=Path(fila["ruta_original"]).is_file(),
        creado=fila["creado"],
    )


def importar(
    conexion: sqlite3.Connection,
    datos: VideoCrear,
    ruta_configurada_ffprobe: Path | None,
    sistema: str,
) -> VideoRespuesta:
    # Se valida el proyecto a través de su servicio, sin leer la tabla proyectos.
    proyectos.obtener(conexion, datos.proyecto_id)

    ruta = validar_ruta_entrada(datos.ruta)
    tamano = ruta.stat().st_size
    metadatos = leer_metadatos(ruta, ruta_configurada_ffprobe, sistema, tamano)

    try:
        video_id = repository.insertar(
            conexion,
            {
                "proyecto_id": datos.proyecto_id,
                "nombre": ruta.name,
                "ruta_original": str(ruta),
                "tamano_bytes": tamano,
                "duracion_segundos": metadatos.duracion_segundos,
                "ancho": metadatos.ancho,
                "alto": metadatos.alto,
                "fps": metadatos.fps,
                "codec_video": metadatos.codec_video,
                "codec_audio": metadatos.codec_audio,
                "formato": metadatos.formato,
            },
        )
    except sqlite3.IntegrityError as error:
        raise Conflicto("Este video ya está registrado en el proyecto.") from error

    return obtener(conexion, video_id)


def listar(conexion: sqlite3.Connection, proyecto_id: int) -> list[VideoRespuesta]:
    proyectos.obtener(conexion, proyecto_id)
    return [_a_respuesta(fila) for fila in repository.listar_por_proyecto(conexion, proyecto_id)]


def obtener(conexion: sqlite3.Connection, video_id: int) -> VideoRespuesta:
    fila = repository.obtener(conexion, video_id)
    if fila is None:
        raise NoEncontrado("El video no existe.")
    return _a_respuesta(fila)


def eliminar(conexion: sqlite3.Connection, video_id: int) -> None:
    if not repository.eliminar(conexion, video_id):
        raise NoEncontrado("El video no existe.")


def ruta_para_transmision(conexion: sqlite3.Connection, video_id: int) -> tuple[Path, str]:
    """Devuelve la ruta del original y su tipo MIME. Verifica que el archivo siga existiendo."""
    fila = repository.obtener(conexion, video_id)
    if fila is None:
        raise NoEncontrado("El video no existe.")

    ruta = Path(fila["ruta_original"])
    if not ruta.is_file():
        raise NoEncontrado("El archivo original ya no está disponible.")

    tipo = EXTENSIONES_ADMITIDAS.get(ruta.suffix.lower(), "application/octet-stream")
    return ruta, tipo

