"""Archivos de fotogramas bajo data/work. No accede a la base de datos.

Cada miniatura va en `work/<video_id>/fotogramas/<tiempo_ms>.jpg`. La escritura pasa por un
temporal `*.tmp` que se renombra con `os.replace`, así que un archivo final nunca queda a medias.
"""

import os
from pathlib import Path

from app.core.errores import NoEncontrado
from app.core.rutas import RaizDatos, RutaNoPermitida
from app.plugins.contrato import ContratoInvalido, FotogramaProducido

TAMANO_MAXIMO_MINIATURA_BYTES = 2 * 1024 * 1024
CABECERA_JPEG = b"\xff\xd8\xff"
SUFIJO_TEMPORAL = ".tmp"


def ruta_relativa_fotograma(video_id: int, tiempo_ms: int) -> str:
    if isinstance(video_id, bool) or not isinstance(video_id, int) or video_id <= 0:
        raise ContratoInvalido("El identificador del video no es válido.")
    if isinstance(tiempo_ms, bool) or not isinstance(tiempo_ms, int) or tiempo_ms < 0:
        raise ContratoInvalido("El tiempo del fotograma debe ser un entero no negativo.")
    return f"work/{video_id}/fotogramas/{tiempo_ms}.jpg"


def directorio_fotogramas_relativo(video_id: int) -> str:
    return f"work/{video_id}/fotogramas"


class AlmacenFotogramasVideo:
    """Implementa `AlmacenFotogramas` del contrato para un video concreto."""

    def __init__(self, raiz: RaizDatos, video_id: int) -> None:
        self._raiz = raiz
        self._video_id = video_id

    def guardar(self, tiempo_ms: int, imagen: bytes) -> FotogramaProducido:
        if not isinstance(imagen, (bytes, bytearray)) or not imagen.startswith(CABECERA_JPEG):
            raise ContratoInvalido("La miniatura debe ser un JPEG.")
        if len(imagen) > TAMANO_MAXIMO_MINIATURA_BYTES:
            raise ContratoInvalido("La miniatura supera el tamaño máximo.")
        relativa = ruta_relativa_fotograma(self._video_id, tiempo_ms)
        destino = self._raiz.resolver(relativa)
        destino.parent.mkdir(parents=True, exist_ok=True)
        temporal = destino.with_name(destino.name + SUFIJO_TEMPORAL)
        temporal.write_bytes(bytes(imagen))
        os.replace(temporal, destino)
        return FotogramaProducido(tiempo_ms=tiempo_ms, ruta_relativa=relativa)


def verificar_fotograma(raiz: RaizDatos, ruta_relativa: str) -> Path:
    """Comprueba que un fotograma registrado sigue en su sitio y devuelve su ruta absoluta.

    `RaizDatos.resolver` resuelve enlaces y junctions antes de comparar, así que una ruta que salga
    de la raíz se rechaza aunque se llegue a ella por un enlace.
    """
    try:
        ruta = raiz.resolver(ruta_relativa)
    except RutaNoPermitida as error:
        raise NoEncontrado("La miniatura no está disponible.") from error
    if not ruta.is_file():
        raise NoEncontrado("La miniatura no está disponible.")
    return ruta


def barrer_huerfanos(raiz: RaizDatos, video_id: int, registradas: set[str]) -> int:
    """Borra los fotogramas del video que no tienen fila y los temporales. Devuelve cuántos borró.

    Solo borra archivos regulares dentro del directorio del video. No sigue enlaces ni borra directorios.
    El llamador debe confirmar que no hay un trabajo en ejecución.
    """
    try:
        directorio = raiz.resolver(directorio_fotogramas_relativo(video_id))
    except RutaNoPermitida:
        return 0
    if not directorio.is_dir() or directorio.is_symlink():
        return 0
    eliminados = 0
    for entrada in directorio.iterdir():
        if entrada.is_symlink() or not entrada.is_file():
            continue
        relativa = entrada.relative_to(raiz.raiz).as_posix()
        if entrada.name.endswith(SUFIJO_TEMPORAL) or relativa not in registradas:
            entrada.unlink(missing_ok=True)
            eliminados += 1
    return eliminados
