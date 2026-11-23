"""Analizador visual con métodos clásicos de OpenCV. Implementa el contrato `Analizador` de `app/plugins/`.

Por cada segmento produce señales de brillo, movimiento y cambio de escena, y guarda fotogramas representativos.
El segmento `[inicio, fin)` posee las muestras cuyo tiempo cae dentro de él. Una muestra previa, que pertenece al
segmento anterior, sirve solo para comparar. Así ningún fotograma se procesa dos veces ni se pierde.
"""
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app.core.configuracion import Configuracion
from app.core.herramientas import resolver_herramienta
from app.core.plataforma import detectar_plataforma
from app.modules.vision import captura, medidas
from app.modules.vision.captura import ErrorVideo
from app.modules.vision.parametros import PARAMETROS_POR_DEFECTO, ParametrosVision, dimensiones_proporcionales
from app.modules.vision.seleccion import CandidatoFotograma, limite_del_segmento, seleccionar
from app.plugins.contrato import (
    AlmacenFotogramas,
    FotogramaProducido,
    ResultadoSegmento,
    SegmentoEntrada,
    Senal,
)
from app.plugins.registro import RegistroAnalizadores

IDENTIFICADOR = "video"
VERSION = "1.0.0"

TIPO_BRILLO = "brillo"
TIPO_MOVIMIENTO = "movimiento"
TIPO_CAMBIO_ESCENA = "cambio_escena"

# Un segmento que entrega menos muestras que las esperadas no es válido. Se tolera perder hasta dos,
# por redondeos de la duración del archivo en el último segmento.
MUESTRAS_FALTANTES_TOLERADAS = 2


@dataclass(frozen=True)
class EstadoPrevioVideo:
    """Lo que el segmento anterior dejó guardado. Lo lee el servicio de trabajos desde la base de datos."""

    ultimo_cambio_ms: int | None
    ultimo_fotograma_ms: int | None
    firma_ultimo_fotograma: np.ndarray | None


def _sin_verificacion() -> None:
    return None


def _ejecutable_ffmpeg(ruta: Path | None) -> Path:
    if ruta is not None:
        return ruta
    # Sin ruta explícita se usa la configuración del proceso y después el PATH, igual que el resto de módulos.
    return resolver_herramienta("ffmpeg", Configuracion().ffmpeg, detectar_plataforma().sistema)


class AnalizadorVideo:
    """Cumple el contrato `Analizador`. Necesita las dimensiones del video para reducir sus fotogramas."""

    def __init__(
        self,
        dimensiones_origen: tuple[int, int] | None = None,
        ffmpeg: Path | None = None,
        verificar: Callable[[], None] = _sin_verificacion,
        parametros: ParametrosVision = PARAMETROS_POR_DEFECTO,
    ) -> None:
        self._dimensiones_origen = dimensiones_origen
        self._ffmpeg = ffmpeg
        self._verificar = verificar
        self._parametros = parametros

    @property
    def id(self) -> str:
        return IDENTIFICADOR

    @property
    def version(self) -> str:
        return VERSION

    @property
    def parametros(self) -> ParametrosVision:
        return self._parametros

    def analizar_segmento(
        self,
        segmento: SegmentoEntrada,
        almacen: AlmacenFotogramas,
        estado_previo: EstadoPrevioVideo | None = None,
    ) -> ResultadoSegmento:
        if self._dimensiones_origen is None:
            raise ErrorVideo("Faltan las dimensiones del video para analizarlo.")
        p = self._parametros
        intervalo = p.intervalo_muestreo_ms
        inicio, fin = segmento.inicio_ms, segmento.fin_ms

        # Primera muestra de la cuadrícula que pertenece a este segmento, y la muestra previa que se usa para comparar.
        primera_propia = -(-inicio // intervalo)
        anclaje = max(0, primera_propia - 1) * intervalo
        esperadas = -(-fin // intervalo) - primera_propia

        ancho_origen, alto_origen = self._dimensiones_origen
        ancho_fotograma, alto_fotograma = dimensiones_proporcionales(
            ancho_origen, alto_origen, p.ancho_fotograma
        )
        ancho_analisis, alto_analisis = dimensiones_proporcionales(
            ancho_fotograma, alto_fotograma, p.ancho_analisis
        )

        ultimo_cambio = estado_previo.ultimo_cambio_ms if estado_previo is not None else None
        senales: list[Senal] = []
        candidatos: list[CandidatoFotograma] = []
        anterior_gris: np.ndarray | None = None
        anterior_tiempo = 0
        propias = 0

        flujo = captura.fotogramas_de_rango(
            _ejecutable_ffmpeg(self._ffmpeg),
            segmento.ruta_video,
            anclaje,
            fin,
            intervalo,
            ancho_fotograma,
            alto_fotograma,
            p.hilos_ffmpeg,
            self._verificar,
        )
        for tiempo, imagen in flujo:
            gris = medidas.reducir_gris(imagen, ancho_analisis, alto_analisis)
            if tiempo < inicio:
                anterior_gris, anterior_tiempo = gris, tiempo
                continue
            propias += 1
            senales.append(Senal(TIPO_BRILLO, tiempo, tiempo, medidas.brillo(gris), p.confianza_brillo))
            if anterior_gris is not None:
                fraccion_escena, fraccion_movimiento = medidas.fracciones_cambiadas(
                    anterior_gris, gris, p.umbral_pixel_cambio_escena, p.umbral_pixel_movimiento
                )
                senales.append(
                    Senal(TIPO_MOVIMIENTO, anterior_tiempo, tiempo, fraccion_movimiento, p.confianza_movimiento)
                )
                es_escena = fraccion_escena >= p.umbral_fraccion_escena and (
                    ultimo_cambio is None or tiempo - ultimo_cambio >= p.intervalo_minimo_escena_ms
                )
                if es_escena:
                    senales.append(
                        Senal(TIPO_CAMBIO_ESCENA, anterior_tiempo, tiempo, fraccion_escena, p.confianza_cambio_escena)
                    )
                    ultimo_cambio = tiempo
                    candidatos.append(self._candidato(tiempo, imagen, 1.0 + fraccion_escena))
                elif fraccion_movimiento >= p.umbral_movimiento_destacado:
                    candidatos.append(self._candidato(tiempo, imagen, fraccion_movimiento))
            anterior_gris, anterior_tiempo = gris, tiempo

        if propias < esperadas - MUESTRAS_FALTANTES_TOLERADAS:
            raise ErrorVideo("El video termina antes de lo que indica su duración.")

        ultimo = self._referencia_previa(estado_previo)
        maximo = limite_del_segmento(p, fin - inicio)
        elegidos = seleccionar(candidatos, p, maximo, ultimo)
        fotogramas: list[FotogramaProducido] = [
            almacen.guardar(candidato.tiempo_ms, medidas.codificar_jpeg(candidato.imagen, p.calidad_jpeg))
            for candidato in elegidos
        ]
        return ResultadoSegmento(senales=tuple(senales), fotogramas=tuple(fotogramas))

    def _candidato(self, tiempo: int, imagen: np.ndarray, puntuacion: float) -> CandidatoFotograma:
        # Se copia la imagen: el búfer de la tubería se reutiliza en la siguiente lectura.
        return CandidatoFotograma(
            tiempo_ms=tiempo,
            puntuacion=float(puntuacion),
            imagen=imagen.copy(),
            firma=medidas.firma(imagen),
        )

    @staticmethod
    def _referencia_previa(estado_previo: EstadoPrevioVideo | None) -> tuple[int, np.ndarray] | None:
        if estado_previo is None or estado_previo.ultimo_fotograma_ms is None:
            return None
        if estado_previo.firma_ultimo_fotograma is None:
            return None
        return estado_previo.ultimo_fotograma_ms, estado_previo.firma_ultimo_fotograma


def registrar(registro: RegistroAnalizadores) -> None:
    """Registra el analizador visual. Si ya está registrado, no hace nada."""
    if not registro.existe(IDENTIFICADOR):
        registro.registrar(AnalizadorVideo())
