"""Energía RMS en ventanas de 200 ms a partir de PCM que entrega FFmpeg.

FFmpeg escribe PCM s16le, mono, 16 kHz, por la salida estándar. Python lee ventana a ventana y no
guarda ningún WAV. La memoria usada por un segmento depende de la ventana, no de la duración.
"""

import subprocess
import tempfile
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

import numpy as np

FRECUENCIA_MUESTREO = 16000
VENTANA_MS = 200
MUESTRAS_POR_VENTANA = FRECUENCIA_MUESTREO * VENTANA_MS // 1000
BYTES_POR_VENTANA = MUESTRAS_POR_VENTANA * 2
ESCALA_16_BITS = 32768.0

# Escala de decibelios usada en todo el analizador: -90 dBFS equivale a 0 y 0 dBFS equivale a 1.
SUELO_DB = -90.0
RANGO_DB = -SUELO_DB

TIEMPO_ESPERA_FFMPEG_SEGUNDOS = 60


class ErrorAudio(RuntimeError):
    """Fallo al leer o analizar el audio. El mensaje no contiene rutas del sistema."""


@dataclass(frozen=True)
class VentanaEnergia:
    inicio_ms: int
    rms: float


def db_desde_rms(rms: float) -> float:
    """Nivel en dBFS. Un silencio digital (RMS cero) vale SUELO_DB."""
    if rms <= 0.0:
        return SUELO_DB
    return max(SUELO_DB, 20.0 * float(np.log10(rms)))


def valor_desde_db(nivel_db: float) -> float:
    """Pasa dBFS al valor normalizado de 0 a 1 que usan las señales."""
    return min(max((nivel_db - SUELO_DB) / RANGO_DB, 0.0), 1.0)


def db_desde_valor(valor: float) -> float:
    """Inversa de `valor_desde_db`."""
    return valor * RANGO_DB + SUELO_DB


def _leer_completo(flujo: BinaryIO, cantidad: int) -> bytes:
    partes: list[bytes] = []
    faltan = cantidad
    while faltan > 0:
        trozo = flujo.read(faltan)
        if not trozo:
            break
        partes.append(trozo)
        faltan -= len(trozo)
    return b"".join(partes)


def ventanas_de_flujo(
    flujo: BinaryIO, inicio_ms: int, verificar: Callable[[], None]
) -> Iterator[VentanaEnergia]:
    """RMS de cada ventana completa del flujo. La cola de menos de 200 ms se descarta.

    `verificar` se llama antes de cada ventana. Si lanza una excepción (por ejemplo, por cancelación),
    el flujo se abandona sin terminar el análisis.
    """
    indice = 0
    while True:
        bloque = _leer_completo(flujo, BYTES_POR_VENTANA)
        if len(bloque) < BYTES_POR_VENTANA:
            return
        verificar()
        muestras = np.frombuffer(bloque, dtype="<i2").astype(np.float64) / ESCALA_16_BITS
        rms = float(np.sqrt(np.mean(np.square(muestras))))
        yield VentanaEnergia(inicio_ms=inicio_ms + indice * VENTANA_MS, rms=rms)
        indice += 1


def _comando_ffmpeg(ejecutable: Path, ruta_video: Path, inicio_ms: int, fin_ms: int) -> list[str]:
    # Lista de argumentos, nunca cadena de shell. Los tiempos llevan tres decimales: son milisegundos exactos.
    return [
        str(ejecutable),
        "-nostdin",
        "-v", "error",
        "-protocol_whitelist", "file,pipe",
        "-ss", f"{inicio_ms / 1000:.3f}",
        "-i", str(ruta_video),
        "-t", f"{(fin_ms - inicio_ms) / 1000:.3f}",
        "-map", "0:a:0",
        "-vn",
        "-ac", "1",
        "-ar", str(FRECUENCIA_MUESTREO),
        "-f", "s16le",
        "pipe:1",
    ]


def _terminar_si_sigue_vivo(proceso: subprocess.Popen) -> None:
    if proceso.poll() is None:
        proceso.kill()
        proceso.wait()


def ventanas_de_rango(
    ejecutable: Path,
    ruta_video: Path,
    inicio_ms: int,
    fin_ms: int,
    verificar: Callable[[], None],
) -> Iterator[VentanaEnergia]:
    """Ventanas de energía de [inicio_ms, fin_ms) del audio del video.

    El stderr de FFmpeg va a un archivo temporal, así que nunca bloquea la tubería. Si FFmpeg falla,
    se lanza ErrorAudio sin el texto de su error, porque puede contener la ruta del archivo.
    """
    comando = _comando_ffmpeg(ejecutable, ruta_video, inicio_ms, fin_ms)
    with tempfile.TemporaryFile() as registro_errores:
        proceso = subprocess.Popen(
            comando,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=registro_errores,
            close_fds=True,
        )
        try:
            assert proceso.stdout is not None
            yield from ventanas_de_flujo(proceso.stdout, inicio_ms, verificar)
            try:
                codigo = proceso.wait(timeout=TIEMPO_ESPERA_FFMPEG_SEGUNDOS)
            except subprocess.TimeoutExpired as error:
                raise ErrorAudio("FFmpeg tardó demasiado en terminar la lectura del audio.") from error
            if codigo != 0:
                raise ErrorAudio("FFmpeg no pudo leer el audio del segmento.")
        finally:
            if proceso.stdout is not None:
                proceso.stdout.close()
            _terminar_si_sigue_vivo(proceso)
