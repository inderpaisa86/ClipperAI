"""Selector nativo de archivos del sistema operativo.

Es el único módulo, junto con plataforma.py y herramientas.py, que contiene ramas por sistema.
El comando se construye desde un script fijo. Ningún dato del cliente entra en el comando.
"""

import base64
import subprocess
import threading
from pathlib import Path

from app.core.errores import Conflicto, NoDisponible, NoSoportado

TIMEOUT_SEGUNDOS = 600
MENSAJE_NO_SOPORTADO = (
    "La selección nativa de archivos no está disponible en este sistema. Escriba la ruta del video."
)

_CANDADO = threading.Lock()

_SCRIPT_WINDOWS = """
Add-Type -AssemblyName System.Windows.Forms
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$dialogo = New-Object System.Windows.Forms.OpenFileDialog
$dialogo.Title = 'Seleccionar video'
$dialogo.Filter = 'Videos|*.mp4;*.m4v;*.mov;*.mkv;*.webm;*.avi|Todos los archivos|*.*'
$dialogo.Multiselect = $false
$propietario = New-Object System.Windows.Forms.Form
$propietario.Text = 'ClipperAI'
$propietario.ShowInTaskbar = $false
$propietario.Opacity = 0
$propietario.TopMost = $true
$propietario.StartPosition = 'CenterScreen'
$propietario.Show()
$propietario.Activate()
if ($dialogo.ShowDialog($propietario) -eq [System.Windows.Forms.DialogResult]::OK) {
    Write-Output $dialogo.FileName
}
"""

_SCRIPT_MACOS = (
    'POSIX path of (choose file with prompt "Seleccionar video" '
    'of type {"public.movie"})'
)

# Código de error de AppleScript que indica que el usuario canceló el diálogo.
_CODIGO_CANCELADO_MACOS = b"-128"


def _comando(sistema: str) -> list[str]:
    if sistema == "windows":
        codificado = base64.b64encode(_SCRIPT_WINDOWS.encode("utf-16-le")).decode("ascii")
        return [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-STA",
            "-EncodedCommand",
            codificado,
        ]
    if sistema == "macos":
        return ["osascript", "-e", _SCRIPT_MACOS]
    raise NoSoportado(MENSAJE_NO_SOPORTADO)


def seleccionar_video(sistema: str) -> Path | None:
    """Abre el selector y devuelve la ruta elegida, o None si el usuario cancela."""
    comando = _comando(sistema)

    if not _CANDADO.acquire(blocking=False):
        raise Conflicto("Ya hay un selector de archivos abierto.")
    try:
        resultado = subprocess.run(
            comando, capture_output=True, timeout=TIMEOUT_SEGUNDOS, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise NoDisponible("No se pudo abrir el selector de archivos.") from error
    finally:
        _CANDADO.release()

    if resultado.returncode != 0:
        if sistema == "macos" and _CODIGO_CANCELADO_MACOS in resultado.stderr:
            return None
        raise NoDisponible("No se pudo abrir el selector de archivos.")

    ruta = resultado.stdout.decode("utf-8", errors="replace").strip()
    return Path(ruta) if ruta else None
