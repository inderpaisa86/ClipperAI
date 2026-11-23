import sqlite3
import stat
from dataclasses import dataclass
from pathlib import Path

from app.core.errores import Conflicto, NoEncontrado, SolicitudInvalida
from app.core.rutas import RaizDatos
from app.db.conexion import transaccion_inmediata
from app.modules.analisis import service as analisis
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


@dataclass(frozen=True)
class DatosAnalisis:
    """Lo que un analizador necesita del video, sin ruta. `duracion_ms` es None si FFprobe no la dio."""

    duracion_ms: int | None
    tiene_audio: bool
    tiene_video: bool = False
    ancho: int | None = None
    alto: int | None = None


def _es_enlace(ruta: Path) -> bool:
    """Enlace simbólico, o junction de Windows (que no requiere privilegios para crearse)."""
    if ruta.is_symlink():
        return True
    es_junction = getattr(ruta, "is_junction", None)
    return es_junction is not None and es_junction()


def _contiene_enlaces(ruta: Path) -> bool:
    """True si la ruta o cualquiera de sus directorios padre es un enlace.

    Un enlace en un directorio intermedio podría redirigir la lectura a un archivo distinto
    del que el usuario eligió. Por eso se revisa toda la cadena, hasta la raíz.
    """
    return any(_es_enlace(parte) for parte in (ruta, *ruta.parents))


def _archivo_accesible(ruta: Path) -> bool:
    """Archivo regular existente sin enlaces en su ruta. Se evalúa en cada uso, no solo al importar."""
    try:
        return ruta.is_file() and not _contiene_enlaces(ruta)
    except OSError:
        return False


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
    if ".." in ruta.parts:
        # Con '..' después de un enlace, el sistema resuelve una ruta distinta de la que se ve.
        raise SolicitudInvalida("La ruta no puede contener '..'.")
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
    if _contiene_enlaces(ruta):
        raise SolicitudInvalida(
            "No se admiten enlaces simbólicos ni accesos directos en la ruta. "
            "Seleccione el archivo original."
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
        nombre_archivo=Path(fila["ruta_original"]).name,
        tamano_bytes=fila["tamano_bytes"],
        duracion_segundos=fila["duracion_segundos"],
        ancho=fila["ancho"],
        alto=fila["alto"],
        fps=fila["fps"],
        codec_video=fila["codec_video"],
        codec_audio=fila["codec_audio"],
        formato=fila["formato"],
        disponible=_archivo_accesible(Path(fila["ruta_original"])),
        creado=fila["creado"],
    )


def importar(
    conexion: sqlite3.Connection,
    proyecto_id: int,
    texto_ruta: str,
    ruta_configurada_ffprobe: Path | None,
    sistema: str,
) -> VideoRespuesta:
    # Se valida el proyecto a través de su servicio, sin leer la tabla proyectos.
    proyectos.obtener(conexion, proyecto_id)
    ruta = validar_ruta_entrada(texto_ruta)
    tamano = ruta.stat().st_size
    metadatos = leer_metadatos(ruta, ruta_configurada_ffprobe, sistema, tamano)
    try:
        video_id = repository.insertar(
            conexion,
            {
                "proyecto_id": proyecto_id,
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


def contar_por_proyecto(conexion: sqlite3.Connection, proyecto_id: int) -> int:
    """Servicio público para otros módulos. Cuenta los videos de un proyecto."""
    return repository.contar_por_proyecto(conexion, proyecto_id)


def contar_por_proyectos(conexion: sqlite3.Connection) -> dict[int, int]:
    """Servicio público para otros módulos. Devuelve {proyecto_id: cantidad} en una sola consulta."""
    return {
        int(fila["proyecto_id"]): int(fila["cantidad"])
        for fila in repository.contar_por_proyectos(conexion)
    }


def existe(conexion: sqlite3.Connection, video_id: int) -> bool:
    """Servicio público para otros módulos. No revisa si el archivo sigue disponible."""
    return repository.obtener(conexion, video_id) is not None


def ids_existentes(conexion: sqlite3.Connection) -> set[int]:
    """Servicio público para otros módulos. Identificadores de todos los videos registrados."""
    return repository.ids(conexion)


def eliminar(conexion: sqlite3.Connection, raiz: RaizDatos, video_id: int) -> None:
    """Elimina el registro del video y sus datos derivados. El archivo original nunca se toca.

    La base de datos cambia en una sola transacción: se borran los análisis del video a través del
    servicio de análisis, y después el registro del video. Los archivos de miniaturas se borran
    cuando la transacción ya está confirmada. Si alguno falla, queda huérfano y la limpieza de
    arranque lo retira. Nunca queda una fila que apunte a un archivo ya borrado.
    """
    with transaccion_inmediata(conexion):
        if repository.obtener(conexion, video_id) is None:
            raise NoEncontrado("El video no existe.")
        analisis.preparar_eliminacion(conexion, video_id)
        repository.eliminar(conexion, video_id)
    analisis.borrar_archivos_derivados(raiz, video_id)


def ruta_para_transmision(conexion: sqlite3.Connection, video_id: int) -> tuple[Path, str]:
    """Devuelve la ruta del original y su tipo MIME. Verifica que el archivo siga existiendo."""
    ruta = ruta_para_analisis(conexion, video_id)
    tipo = EXTENSIONES_ADMITIDAS.get(ruta.suffix.lower(), "application/octet-stream")
    return ruta, tipo


def ruta_para_analisis(conexion: sqlite3.Connection, video_id: int) -> Path:
    """Ruta del original para procesos internos del backend. Nunca se devuelve por la API."""
    fila = repository.obtener(conexion, video_id)
    if fila is None:
        raise NoEncontrado("El video no existe.")
    ruta = Path(fila["ruta_original"])
    if not _archivo_accesible(ruta):
        raise NoEncontrado("El archivo original ya no está disponible.")
    return ruta


def datos_para_analisis(conexion: sqlite3.Connection, video_id: int) -> DatosAnalisis:
    """Servicio público para analizadores. Duración en milisegundos enteros y si hay pista de audio."""
    fila = repository.obtener(conexion, video_id)
    if fila is None:
        raise NoEncontrado("El video no existe.")
    duracion = fila["duracion_segundos"]
    return DatosAnalisis(
        duracion_ms=None if duracion is None else round(float(duracion) * 1000),
        tiene_audio=fila["codec_audio"] is not None,
        tiene_video=fila["codec_video"] is not None,
        ancho=fila["ancho"],
        alto=fila["alto"],
    )
