"""Parámetros del analizador visual. Son el único lugar donde se fijan frecuencias, tamaños y umbrales.

Los valores son los de la versión 1.0.0 del analizador (D-058 a D-061). Cambiar cualquiera de ellos cambia
los resultados, así que exige subir la versión del analizador para invalidar los anteriores (D-015).
"""
from dataclasses import dataclass

DURACION_MINUTO_MS = 60_000


@dataclass(frozen=True)
class ParametrosVision:
    # Muestreo. Cada muestra es un fotograma en la cuadrícula global t = k * intervalo_muestreo_ms.
    intervalo_muestreo_ms: int = 1000
    duracion_segmento_ms: int = DURACION_MINUTO_MS
    hilos_ffmpeg: int = 8

    # Tamaños. El fotograma se reduce conservando la relación de aspecto. El análisis usa una copia en gris.
    ancho_fotograma: int = 320
    ancho_analisis: int = 160

    # Cambio de escena: fracción de píxeles que cambian más de `umbral_pixel_cambio_escena` niveles de gris.
    umbral_pixel_cambio_escena: int = 30
    umbral_fraccion_escena: float = 0.35
    intervalo_minimo_escena_ms: int = 2000

    # Movimiento: fracción de píxeles que cambian más de `umbral_pixel_movimiento` niveles de gris.
    # Un umbral alto ignora el ruido de compresión, que suele cambiar pocos niveles.
    umbral_pixel_movimiento: int = 20

    # Fotogramas representativos.
    maximo_fotogramas_por_minuto: int = 6
    umbral_movimiento_destacado: float = 0.10
    separacion_minima_fotogramas_ms: int = 5000
    diferencia_minima_fotogramas: float = 0.05
    calidad_jpeg: int = 85

    # Confianza fija por método (D-059).
    confianza_cambio_escena: float = 0.8
    confianza_movimiento: float = 0.6
    confianza_brillo: float = 1.0

    def __post_init__(self) -> None:
        enteros_positivos = (
            self.intervalo_muestreo_ms,
            self.duracion_segmento_ms,
            self.hilos_ffmpeg,
            self.ancho_analisis,
            self.intervalo_minimo_escena_ms,
            self.maximo_fotogramas_por_minuto,
            self.separacion_minima_fotogramas_ms,
        )
        if any(valor <= 0 for valor in enteros_positivos):
            raise ValueError("Los parámetros de muestreo y límites deben ser positivos.")
        if self.ancho_fotograma < self.ancho_analisis:
            raise ValueError("El fotograma no puede ser más estrecho que la imagen de análisis.")
        if self.ancho_analisis < 16:
            raise ValueError("La imagen de análisis necesita al menos 16 píxeles de ancho.")
        if not 0 < self.umbral_pixel_cambio_escena <= 255 or not 0 < self.umbral_pixel_movimiento <= 255:
            raise ValueError("Los umbrales de píxel deben estar entre 1 y 255.")
        proporciones = (
            self.umbral_fraccion_escena,
            self.umbral_movimiento_destacado,
            self.diferencia_minima_fotogramas,
            self.confianza_cambio_escena,
            self.confianza_movimiento,
            self.confianza_brillo,
        )
        if any(not 0.0 <= valor <= 1.0 for valor in proporciones):
            raise ValueError("Los umbrales y confianzas deben estar entre 0 y 1.")
        if not 1 <= self.calidad_jpeg <= 100:
            raise ValueError("La calidad JPEG debe estar entre 1 y 100.")


PARAMETROS_POR_DEFECTO = ParametrosVision()


def dimensiones_proporcionales(ancho_origen: int, alto_origen: int, ancho_maximo: int) -> tuple[int, int]:
    """Ancho y alto pares que conservan la relación de aspecto y no superan `ancho_maximo`.

    Nunca amplía la imagen: si el origen es más estrecho que el máximo, usa el ancho del origen.
    """
    ancho = min(ancho_maximo, ancho_origen)
    ancho -= ancho % 2
    alto = round(alto_origen * ancho / ancho_origen)
    alto -= alto % 2
    return max(ancho, 2), max(alto, 2)
