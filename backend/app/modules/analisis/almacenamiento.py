"""Archivos de fotogramas bajo data/work. No accede a la base de datos.

Cada miniatura va en `work/<video_id>/fotogramas/<tiempo_ms>.jpg`. La escritura pasa por un
temporal `*.tmp` que se renombra con `os.replace`, así que un archivo final nunca queda a medias.

Las operaciones de borrado no siguen enlaces simbólicos ni junctions en ninguna parte de la ruta.
Solo borran miniaturas `.jpg` y temporales `.tmp` dentro de `work/<video_id>/fotogramas`.
"""

import os
from pathlib import Path

from app.core.errores import NoEncontrado
from app.core.rutas import RaizDatos, RutaNoPermitida
from app.plugins.contrato import ContratoInvalido, FotogramaProducido

TAMANO_MAXIMO_MINIATURA_BYTES = 2 * 1024 * 1024
CABECERA_JPEG = b"\xff\xd8\xff"
SUFIJO_TEMPORAL = ".tmp"
SUFIJO_MINIATURA = ".jpg"
DIRECTORIO_WORK = "work"


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


def es_enlace(ruta: Path) -> bool:
    """Enlace simbólico o junction de Windows. `is_symlink` no detecta los junctions."""
    if ruta.is_symlink():
        return True
    es_junction = getattr(ruta, "is_junction", None)
    return es_junction is not None and es_junction()


def _directorio_seguro(raiz: RaizDatos, *partes: str) -> Path | None:
    """Ruta absoluta de un directorio dentro de la raíz, si toda la cadena existe y no contiene enlaces.

    Devuelve None si algún tramo no existe, es enlace o sale de la raíz.
    """
    actual = raiz.raiz
    for parte in partes:
        actual = actual / parte
        if es_enlace(actual) or not actual.is_dir():
            return None
    return actual


def _borrar_miniaturas_en(directorio: Path) -> tuple[int, int]:
    """Borra miniaturas y temporales de un directorio. Devuelve (borrados, fallidos). No borra subdirectorios."""
    borrados = 0
    fallidos = 0
    for entrada in directorio.iterdir():
        nombre = entrada.name
        if es_enlace(entrada) or not entrada.is_file():
            continue
        if not (nombre.endswith(SUFIJO_MINIATURA) or nombre.endswith(SUFIJO_TEMPORAL)):
            continue
        try:
            entrada.unlink()
            borrados += 1
        except OSError:
            fallidos += 1
    return borrados, fallidos


def _quitar_directorio_si_vacio(directorio: Path) -> None:
    try:
        directorio.rmdir()
    except OSError:
        # Con contenido ajeno o bloqueado, se deja como está.
        return


def borrar_fotogramas_de_video(raiz: RaizDatos, video_id: int) -> tuple[int, int]:
    """Borra las miniaturas y temporales de un video, y sus directorios si quedan vacíos.

    Devuelve (borrados, fallidos). Un fallo no detiene el resto: el archivo queda huérfano y la
    limpieza de arranque lo retira más tarde.
    """
    directorio = _directorio_seguro(raiz, DIRECTORIO_WORK, str(video_id), "fotogramas")
    if directorio is None:
        return 0, 0
    borrados, fallidos = _borrar_miniaturas_en(directorio)
    _quitar_directorio_si_vacio(directorio)
    _quitar_directorio_si_vacio(directorio.parent)
    return borrados, fallidos


def barrer_huerfanos(raiz: RaizDatos, video_id: int, registradas: set[str]) -> int:
    """Borra los fotogramas del video que no tienen fila y los temporales. Devuelve cuántos borró.

    El llamador debe confirmar que no hay un trabajo en ejecución.
    """
    directorio = _directorio_seguro(raiz, DIRECTORIO_WORK, str(video_id), "fotogramas")
    if directorio is None:
        return 0
    eliminados = 0
    for entrada in directorio.iterdir():
        if es_enlace(entrada) or not entrada.is_file():
            continue
        relativa = entrada.relative_to(raiz.raiz).as_posix()
        if entrada.name.endswith(SUFIJO_TEMPORAL) or relativa not in registradas:
            entrada.unlink(missing_ok=True)
            eliminados += 1
    return eliminados


def barrer_videos_eliminados(raiz: RaizDatos, existentes: set[int]) -> tuple[int, int]:
    """Borra miniaturas de videos que ya no existen en la base. Devuelve (borrados, fallidos).

    Solo mira directorios `work/<número>` y solo borra miniaturas y temporales dentro de `fotogramas`.
    Los directorios cuyo nombre no es un número, o que no tienen video registrado pero contienen
    otra cosa, no se tocan.
    """
    raiz_work = _directorio_seguro(raiz, DIRECTORIO_WORK)
    if raiz_work is None:
        return 0, 0
    total_borrados = 0
    total_fallidos = 0
    for directorio_video in raiz_work.iterdir():
        if not directorio_video.name.isdigit() or es_enlace(directorio_video):
            continue
        if not directorio_video.is_dir() or int(directorio_video.name) in existentes:
            continue
        borrados, fallidos = borrar_fotogramas_de_video(raiz, int(directorio_video.name))
        total_borrados += borrados
        total_fallidos += fallidos
        _quitar_directorio_si_vacio(directorio_video)
    return total_borrados, total_fallidos

