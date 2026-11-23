"""Selección de fotogramas representativos dentro de un segmento.

Un candidato es un fotograma con un cambio de escena aceptado o con movimiento destacado. Se eligen primero
los de mayor puntuación. Un candidato se descarta si queda demasiado cerca en el tiempo, o si se parece a un
fotograma ya elegido. La referencia incluye el último fotograma guardado antes del segmento, para que los
bordes entre segmentos no produzcan duplicados.
"""
from dataclasses import dataclass

import numpy as np

from app.modules.vision import medidas
from app.modules.vision.parametros import ParametrosVision


@dataclass(frozen=True)
class CandidatoFotograma:
    tiempo_ms: int
    puntuacion: float
    imagen: np.ndarray
    firma: np.ndarray


def limite_del_segmento(parametros: ParametrosVision, duracion_ms: int) -> int:
    """Número máximo de fotogramas de un segmento. Es proporcional a su duración: 6 por minuto, al menos 1."""
    proporcional = parametros.maximo_fotogramas_por_minuto * duracion_ms / 60_000
    return max(1, round(proporcional))


def seleccionar(
    candidatos: list[CandidatoFotograma],
    parametros: ParametrosVision,
    maximo: int,
    ultimo: tuple[int, np.ndarray] | None,
) -> list[CandidatoFotograma]:
    """Elige hasta `maximo` candidatos, en orden cronológico.

    `ultimo` es (tiempo_ms, firma) del último fotograma guardado antes del segmento, o None si no hay ninguno.
    """
    referencias: list[tuple[int, np.ndarray]] = [ultimo] if ultimo is not None else []
    elegidos: list[CandidatoFotograma] = []
    ordenados = sorted(candidatos, key=lambda candidato: (-candidato.puntuacion, candidato.tiempo_ms))
    for candidato in ordenados:
        if len(elegidos) >= maximo:
            break
        if any(
            abs(candidato.tiempo_ms - tiempo) < parametros.separacion_minima_fotogramas_ms
            for tiempo, _ in referencias
        ):
            continue
        if any(
            medidas.distancia_firmas(candidato.firma, firma_previa) < parametros.diferencia_minima_fotogramas
            for _, firma_previa in referencias
        ):
            continue
        elegidos.append(candidato)
        referencias.append((candidato.tiempo_ms, candidato.firma))
    return sorted(elegidos, key=lambda candidato: candidato.tiempo_ms)
