"""Adaptador del analizador de audio. Implementa el contrato `Analizador` de `app/plugins/`."""

from collections.abc import Callable
from pathlib import Path

from app.core.configuracion import Configuracion
from app.core.herramientas import resolver_herramienta
from app.core.plataforma import detectar_plataforma
from app.modules.audio import energia
from app.modules.audio.senales import senales_de_energia
from app.plugins.contrato import (
    AlmacenFotogramas,
    ContratoInvalido,
    FotogramaProducido,
    ResultadoSegmento,
    SegmentoEntrada,
)
from app.plugins.registro import RegistroAnalizadores

IDENTIFICADOR = "audio"
VERSION = "1.0.0"


def _sin_verificacion() -> None:
    return None


class _AlmacenSinFotogramas:
    """El analizador de audio no genera miniaturas. Si alguien intenta guardar una, falla."""

    def guardar(self, tiempo_ms: int, imagen: bytes) -> FotogramaProducido:
        raise ContratoInvalido("El analizador de audio no genera miniaturas.")


class AnalizadorAudio:
    """Cumple el contrato `Analizador`. `verificar` se llama durante la lectura para detectar cancelaciones."""

    def __init__(
        self,
        ffmpeg: Path | None = None,
        verificar: Callable[[], None] = _sin_verificacion,
    ) -> None:
        self._ffmpeg = ffmpeg
        self._verificar = verificar

    @property
    def id(self) -> str:
        return IDENTIFICADOR

    @property
    def version(self) -> str:
        return VERSION

    def analizar_segmento(
        self, segmento: SegmentoEntrada, almacen: AlmacenFotogramas = _AlmacenSinFotogramas()
    ) -> ResultadoSegmento:
        ventanas = energia.ventanas_de_rango(
            self._ejecutable_ffmpeg(),
            segmento.ruta_video,
            segmento.inicio_ms,
            segmento.fin_ms,
            self._verificar,
        )
        return ResultadoSegmento(senales=tuple(senales_de_energia(ventanas)))

    def _ejecutable_ffmpeg(self) -> Path:
        if self._ffmpeg is None:
            # Sin ruta explícita se usa la configuración del proceso y después el PATH, igual que FFprobe.
            return resolver_herramienta(
                "ffmpeg", Configuracion().ffmpeg, detectar_plataforma().sistema
            )
        return self._ffmpeg


def registrar(registro: RegistroAnalizadores) -> None:
    """Registra el analizador de audio. Si ya está registrado, no hace nada."""
    if not registro.existe(IDENTIFICADOR):
        registro.registrar(AnalizadorAudio())

