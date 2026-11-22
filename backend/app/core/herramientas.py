import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


class HerramientaNoDisponible(RuntimeError):
    pass


_INSTALACION_FFMPEG = {
    "windows": "Instale FFmpeg con 'winget install Gyan.FFmpeg' o configure CLIPPERAI_FFMPEG.",
    "macos": "Instale FFmpeg con 'brew install ffmpeg' o configure CLIPPERAI_FFMPEG.",
}
_INSTALACION_GENERICA = "Instale FFmpeg 9.1 y agréguelo al PATH, o configure CLIPPERAI_FFMPEG."


def instruccion_instalacion(sistema: str) -> str:
    return _INSTALACION_FFMPEG.get(sistema, _INSTALACION_GENERICA)


def resolver_herramienta(nombre: str, ruta_configurada: Path | None, sistema: str) -> Path:
    """Devuelve la ruta del ejecutable. No hace búsqueda alternativa si la ruta configurada falla."""
    if ruta_configurada is not None:
        if ruta_configurada.is_file():
            return ruta_configurada
        raise HerramientaNoDisponible(
            f"La ruta configurada para {nombre} no existe: {ruta_configurada}"
        )

    encontrada = shutil.which(nombre)
    if encontrada is not None:
        return Path(encontrada)

    raise HerramientaNoDisponible(
        f"No se encontró {nombre}. {instruccion_instalacion(sistema)}"
    )


def verificar_herramienta(ruta: Path) -> str:
    """Ejecuta '<herramienta> -version' con lista de argumentos y devuelve la primera línea."""
    try:
        resultado = subprocess.run(
            [str(ruta), "-version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise HerramientaNoDisponible(f"No se pudo ejecutar {ruta}: {error}") from error

    lineas = resultado.stdout.splitlines()
    if resultado.returncode != 0 or not lineas:
        raise HerramientaNoDisponible(f"{ruta} no respondió a -version correctamente.")
    return lineas[0]


@dataclass(frozen=True)
class DiagnosticoHerramienta:
    disponible: bool
    version: str | None
    mensaje: str | None


def diagnosticar_herramienta(
    nombre: str, ruta_configurada: Path | None, sistema: str
) -> DiagnosticoHerramienta:
    try:
        ruta = resolver_herramienta(nombre, ruta_configurada, sistema)
        version = verificar_herramienta(ruta)
    except HerramientaNoDisponible as error:
        return DiagnosticoHerramienta(disponible=False, version=None, mensaje=str(error))
    return DiagnosticoHerramienta(disponible=True, version=version, mensaje=None)
