import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

TAMANO_BLOQUE = 1024 * 1024
_PATRON_RANGO = re.compile(r"(\d*)-(\d*)")


class RangoNoSatisfacible(ValueError):
    """La cabecera Range es sintácticamente inválida o queda fuera del archivo. Responde 416."""


@dataclass(frozen=True)
class RangoBytes:
    inicio: int
    fin: int  # Inclusivo, como en Content-Range.

    @property
    def longitud(self) -> int:
        return self.fin - self.inicio + 1


def interpretar_rango(cabecera: str | None, tamano: int) -> RangoBytes | None:
    """Interpreta una cabecera Range de una sola unidad 'bytes'.

    Devuelve None cuando debe servirse el archivo completo: sin cabecera, unidad distinta
    de bytes o varios rangos. Lanza RangoNoSatisfacible cuando el rango no es válido.
    """
    if not cabecera:
        return None

    unidad, _, especificacion = cabecera.strip().partition("=")
    if unidad.strip().lower() != "bytes":
        return None
    if "," in especificacion:
        return None

    coincidencia = _PATRON_RANGO.fullmatch(especificacion.strip())
    if coincidencia is None:
        raise RangoNoSatisfacible("Rango con formato inválido.")

    inicio_texto, fin_texto = coincidencia.groups()
    if inicio_texto == "" and fin_texto == "":
        raise RangoNoSatisfacible("Rango vacío.")
    if tamano <= 0:
        raise RangoNoSatisfacible("El archivo está vacío.")

    if inicio_texto == "":
        # Sufijo: los últimos N bytes.
        sufijo = int(fin_texto)
        if sufijo == 0:
            raise RangoNoSatisfacible("Sufijo de longitud cero.")
        return RangoBytes(max(tamano - sufijo, 0), tamano - 1)

    inicio = int(inicio_texto)
    if inicio >= tamano:
        raise RangoNoSatisfacible("El inicio del rango supera el tamaño del archivo.")

    if fin_texto == "":
        return RangoBytes(inicio, tamano - 1)

    fin = int(fin_texto)
    if fin < inicio:
        raise RangoNoSatisfacible("El fin del rango es menor que el inicio.")
    return RangoBytes(inicio, min(fin, tamano - 1))


def iterar_archivo(ruta: Path, inicio: int, fin: int) -> Iterator[bytes]:
    """Entrega los bytes [inicio, fin] del archivo en bloques. Nunca carga el archivo completo."""
    restante = fin - inicio + 1
    if restante <= 0:
        return
    with open(ruta, "rb") as archivo:
        archivo.seek(inicio)
        while restante > 0:
            bloque = archivo.read(min(TAMANO_BLOQUE, restante))
            if not bloque:
                break
            restante -= len(bloque)
            yield bloque
