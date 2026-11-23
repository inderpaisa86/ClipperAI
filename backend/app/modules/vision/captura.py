"""Fotogramas de un rango del video, decodificados por FFmpeg en una tubería.

FFmpeg muestrea a la cuadrícula del análisis, reduce el tamaño y entrega imágenes BGR crudas por la salida
estándar. Python lee una imagen cada vez. Ningún fotograma completo del video pasa por memoria, y ningún
archivo intermedio se escribe en disco.
"""
import subprocess
import tempfile
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import BinaryIO

import numpy as np

TIEMPO_ESPERA_FFMPEG_SEGUNDOS = 120
CANALES_BGR = 3


class ErrorVideo(RuntimeError):
    """Fallo al leer o analizar el video. El mensaje no contiene rutas del sistema."""


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


def _comando_ffmpeg(
    ejecutable: Path,
    ruta_video: Path,
    anclaje_ms: int,
    duracion_ms: int,
    intervalo_ms: int,
    ancho: int,
    alto: int,
    hilos: int,
) -> list[str]:
    # Lista de argumentos, nunca cadena de shell. Los tiempos llevan tres decimales: son milisegundos exactos.
    # `fps` fija la cuadrícula: un fotograma por intervalo, contado desde el punto de inicio.
    return [
        str(ejecutable),
        "-nostdin",
        "-v", "error",
        "-protocol_whitelist", "file,pipe",
        "-threads", str(hilos),
        "-ss", f"{anclaje_ms / 1000:.3f}",
        "-i", str(ruta_video),
        "-t", f"{duracion_ms / 1000:.3f}",
        "-map", "0:v:0",
        "-an",
        "-sn",
        "-dn",
        "-vf", f"fps=1000/{intervalo_ms},scale={ancho}:{alto}:flags=area",
        "-pix_fmt", "bgr24",
        "-f", "rawvideo",
        "pipe:1",
    ]


def fotogramas_de_rango(
    ejecutable: Path,
    ruta_video: Path,
    anclaje_ms: int,
    fin_ms: int,
    intervalo_ms: int,
    ancho: int,
    alto: int,
    hilos: int,
    verificar: Callable[[], None],
) -> Iterator[tuple[int, np.ndarray]]:
    """Fotogramas BGR de [anclaje_ms, fin_ms) muestreados cada `intervalo_ms`.

    Entrega (tiempo_ms, imagen). El tiempo es el de la cuadrícula, no el del fotograma real, así que su error
    es como máximo una duración de fotograma del video. `verificar` se llama antes de cada imagen. Si lanza
    una excepción, FFmpeg se termina.
    El stderr de FFmpeg va a un archivo temporal, así que nunca bloquea la tubería. Si FFmpeg falla, se lanza
    ErrorVideo sin el texto de su error, porque puede contener la ruta del archivo.
    """
    comando = _comando_ffmpeg(
        ejecutable, ruta_video, anclaje_ms, fin_ms - anclaje_ms, intervalo_ms, ancho, alto, hilos
    )
    tamano = ancho * alto * CANALES_BGR
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
            indice = 0
            while True:
                bloque = _leer_completo(proceso.stdout, tamano)
                if len(bloque) < tamano:
                    break
                verificar()
                imagen = np.frombuffer(bloque, dtype=np.uint8).reshape(alto, ancho, CANALES_BGR)
                yield anclaje_ms + indice * intervalo_ms, imagen
                indice += 1
            try:
                codigo = proceso.wait(timeout=TIEMPO_ESPERA_FFMPEG_SEGUNDOS)
            except subprocess.TimeoutExpired as error:
                raise ErrorVideo("FFmpeg tardó demasiado en terminar la lectura del video.") from error
            if codigo != 0:
                raise ErrorVideo("FFmpeg no pudo leer el video en este segmento.")
        finally:
            if proceso.stdout is not None:
                proceso.stdout.close()
            if proceso.poll() is None:
                proceso.kill()
                proceso.wait()
