"""Contrato común de los analizadores.

Un analizador lee un segmento del video original y devuelve señales normalizadas y fotogramas.
No conoce la base de datos, ni el motor de puntuación, ni el resto de analizadores. Para guardar
una miniatura usa el almacén que recibe como argumento. Los tiempos son enteros en milisegundos.
"""

import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

PATRON_IDENTIFICADOR = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
LONGITUD_VERSION_MAXIMA = 32

# Vocabulario cerrado de tipos de señal. Es la única fuente de verdad: el proxy (lib/proxy/destinos.ts)
# debe tener la misma lista y una prueba lo verifica. Agregar un tipo exige una decisión registrada.
TIPOS_SENAL_PERMITIDOS: frozenset[str] = frozenset(
    {"energia_audio", "silencio", "cambio_intensidad"}
)


class ContratoInvalido(ValueError):
    """Un dato o un objeto no cumple el contrato de analizadores."""


def _entero_en_milisegundos(valor: object, nombre: str) -> int:
    if isinstance(valor, bool) or not isinstance(valor, int):
        raise ContratoInvalido(f"{nombre} debe ser un entero en milisegundos.")
    if valor < 0:
        raise ContratoInvalido(f"{nombre} no puede ser negativo.")
    return valor


def _proporcion(valor: object, nombre: str) -> float:
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        raise ContratoInvalido(f"{nombre} debe ser un número entre 0 y 1.")
    if not math.isfinite(valor) or not 0 <= valor <= 1:
        raise ContratoInvalido(f"{nombre} debe estar entre 0 y 1.")
    return float(valor)


@dataclass(frozen=True)
class Senal:
    """Valor de un analizador sobre un intervalo de tiempo.

    `valor` es la intensidad de la señal y `confianza` es la seguridad del analizador. Ambos van de 0 a 1.
    """

    tipo: str
    inicio_ms: int
    fin_ms: int
    valor: float
    confianza: float

    def __post_init__(self) -> None:
        if not isinstance(self.tipo, str) or not PATRON_IDENTIFICADOR.fullmatch(self.tipo):
            raise ContratoInvalido("El tipo de señal solo admite minúsculas, números y guion bajo.")
        if self.tipo not in TIPOS_SENAL_PERMITIDOS:
            raise ContratoInvalido("El tipo de señal no está en el vocabulario permitido.")
        inicio = _entero_en_milisegundos(self.inicio_ms, "inicio_ms")
        fin = _entero_en_milisegundos(self.fin_ms, "fin_ms")
        if fin < inicio:
            raise ContratoInvalido("fin_ms no puede ser menor que inicio_ms.")
        _proporcion(self.valor, "valor")
        _proporcion(self.confianza, "confianza")


@dataclass(frozen=True)
class FotogramaProducido:
    """Fotograma ya escrito en el almacén. `ruta_relativa` la asigna el almacén, nunca el analizador."""

    tiempo_ms: int
    ruta_relativa: str

    def __post_init__(self) -> None:
        _entero_en_milisegundos(self.tiempo_ms, "tiempo_ms")
        if not isinstance(self.ruta_relativa, str) or not self.ruta_relativa:
            raise ContratoInvalido("La ruta del fotograma no puede estar vacía.")


@dataclass(frozen=True)
class SegmentoEntrada:
    """Datos de un segmento que recibe el analizador. Es de solo lectura."""

    ruta_video: Path
    inicio_ms: int
    fin_ms: int

    def __post_init__(self) -> None:
        inicio = _entero_en_milisegundos(self.inicio_ms, "inicio_ms")
        fin = _entero_en_milisegundos(self.fin_ms, "fin_ms")
        if fin <= inicio:
            raise ContratoInvalido("El segmento debe tener duración positiva.")


@dataclass(frozen=True)
class ResultadoSegmento:
    senales: tuple[Senal, ...] = ()
    fotogramas: tuple[FotogramaProducido, ...] = ()


class AlmacenFotogramas(Protocol):
    """Guarda una miniatura JPEG de forma atómica y devuelve su registro."""

    def guardar(self, tiempo_ms: int, imagen: bytes) -> FotogramaProducido: ...


@runtime_checkable
class Analizador(Protocol):
    """Contrato que cumple cada analizador. `version` cambia cuando cambian sus resultados."""

    @property
    def id(self) -> str: ...

    @property
    def version(self) -> str: ...

    def analizar_segmento(
        self, segmento: SegmentoEntrada, almacen: AlmacenFotogramas
    ) -> ResultadoSegmento: ...
