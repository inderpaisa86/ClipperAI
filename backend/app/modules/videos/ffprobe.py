import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.errores import NoDisponible, SolicitudInvalida
from app.core.herramientas import HerramientaNoDisponible, resolver_herramienta

TIMEOUT_SEGUNDOS = 60


@dataclass(frozen=True)
class MetadatosVideo:
    formato: str
    duracion_segundos: float | None
    ancho: int
    alto: int
    fps: float | None
    codec_video: str
    codec_audio: str | None


def leer_metadatos(
    ruta: Path, ruta_configurada: Path | None, sistema: str, tamano_bytes: int
) -> MetadatosVideo:
    """Ejecuta FFprobe con lista de argumentos y devuelve los metadatos del primer flujo de video."""
    try:
        ejecutable = resolver_herramienta("ffprobe", ruta_configurada, sistema)
    except HerramientaNoDisponible as error:
        raise NoDisponible(str(error)) from error

    # Solo archivos locales: un nombre con esquema (concat:, http:, etc.) no puede leer otra fuente.
    comando = [
        str(ejecutable),
        "-v", "error",
        "-protocol_whitelist", "file",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        "-i", str(ruta),
    ]
    try:
        resultado = subprocess.run(
            comando, capture_output=True, timeout=TIMEOUT_SEGUNDOS, check=False
        )
    except subprocess.TimeoutExpired as error:
        raise SolicitudInvalida("FFprobe tardó demasiado en leer el archivo.") from error
    except OSError as error:
        raise NoDisponible("No se pudo ejecutar FFprobe.") from error

    if resultado.returncode != 0:
        raise SolicitudInvalida(
            "FFprobe no pudo leer el archivo. Puede estar dañado o en un formato no compatible."
        )

    try:
        datos = json.loads(resultado.stdout.decode("utf-8", errors="replace"))
    except ValueError as error:
        raise SolicitudInvalida("La salida de FFprobe no es válida.") from error

    return interpretar_metadatos(datos, tamano_bytes)


def interpretar_metadatos(datos: dict[str, Any], tamano_bytes: int) -> MetadatosVideo:
    """Convierte la salida JSON de FFprobe en metadatos. Función pura, sin acceso al disco."""
    flujos = datos.get("streams") or []
    video = next(
        (
            flujo
            for flujo in flujos
            if flujo.get("codec_type") == "video"
            and (flujo.get("disposition") or {}).get("attached_pic") != 1
        ),
        None,
    )
    if video is None:
        raise SolicitudInvalida("El archivo no contiene una pista de video.")

    audio = next((flujo for flujo in flujos if flujo.get("codec_type") == "audio"), None)
    formato = datos.get("format") or {}

    ancho = _entero(video.get("width"))
    alto = _entero(video.get("height"))
    if ancho is None or alto is None:
        raise SolicitudInvalida("No se pudo determinar la resolución del video.")

    duracion = _decimal(formato.get("duration")) or _decimal(video.get("duration"))

    return MetadatosVideo(
        formato=str(formato.get("format_name") or "desconocido"),
        duracion_segundos=duracion,
        ancho=ancho,
        alto=alto,
        fps=_fps(video.get("avg_frame_rate")) or _fps(video.get("r_frame_rate")),
        codec_video=str(video.get("codec_name") or "desconocido"),
        codec_audio=str(audio["codec_name"]) if audio and audio.get("codec_name") else None,
    )


def _entero(valor: Any) -> int | None:
    try:
        numero = int(valor)
    except (TypeError, ValueError):
        return None
    return numero if numero > 0 else None


def _decimal(valor: Any) -> float | None:
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    return numero if numero > 0 else None


def _fps(texto: Any) -> float | None:
    """Convierte fracciones como '30000/1001' en 29.97. Devuelve None si la fracción no es válida."""
    if not isinstance(texto, str) or "/" not in texto:
        return None
    numerador, _, denominador = texto.partition("/")
    try:
        n = float(numerador)
        d = float(denominador)
    except ValueError:
        return None
    if n <= 0 or d <= 0:
        return None
    return round(n / d, 3)
