"""Vocabulario de señales de audio y reglas que las calculan. Funciones puras, sin disco ni base de datos.

Vocabulario (identificadores estables, versión 1.0.0 del analizador):

- `energia_audio`: nivel medio de cada ventana de 200 ms. Valor normalizado de 0 a 1, donde 0 es
  -90 dBFS o menos y 1 es 0 dBFS. Confianza 1.
- `silencio`: intervalo continuo de al menos 500 ms con nivel bajo el umbral adaptativo del video.
  Valor = profundidad relativa del silencio: (umbral - nivel medio en dB) / 20, acotado a 0 y 1.
  Confianza 1.
- `cambio_intensidad`: par de ventanas consecutivas cuyo nivel cambia al menos 12 dB. Abarca las
  dos ventanas (400 ms). Valor = |cambio en dB| / 24, acotado a 0 y 1. Confianza 1.

Todos los tiempos son enteros en milisegundos. La confianza es 1 porque estas señales se calculan
sin estimación. Un analizador que estime la confianza usará valores menores.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

import numpy as np

from app.modules.audio.energia import VENTANA_MS, VentanaEnergia, db_desde_rms, valor_desde_db
from app.plugins.contrato import TIPOS_SENAL_PERMITIDOS, Senal

TIPO_ENERGIA = "energia_audio"
TIPO_SILENCIO = "silencio"
TIPO_CAMBIO_INTENSIDAD = "cambio_intensidad"
TIPOS_AUDIO = (TIPO_ENERGIA, TIPO_SILENCIO, TIPO_CAMBIO_INTENSIDAD)

UMBRAL_MINIMO_DB = -55.0
UMBRAL_MAXIMO_DB = -35.0
PERCENTIL_SUELO = 10.0
MARGEN_SOBRE_SUELO_DB = 12.0
DURACION_MINIMA_SILENCIO_MS = 500
PROFUNDIDAD_SILENCIO_COMPLETA_DB = 20.0
SALTO_MINIMO_DB = 12.0
SALTO_COMPLETO_DB = 24.0
CONFIANZA_DETERMINISTA = 1.0


@dataclass(frozen=True)
class PuntoEnergia:
    """Nivel de una ventana ya consolidada. `nivel_db` es el nivel medio en dBFS."""

    inicio_ms: int
    fin_ms: int
    nivel_db: float


def _acotar(valor: float) -> float:
    return min(max(valor, 0.0), 1.0)


def senales_de_energia(ventanas: Iterable[VentanaEnergia]) -> list[Senal]:
    """Una señal `energia_audio` por ventana."""
    return [
        Senal(
            tipo=TIPO_ENERGIA,
            inicio_ms=ventana.inicio_ms,
            fin_ms=ventana.inicio_ms + VENTANA_MS,
            valor=valor_desde_db(db_desde_rms(ventana.rms)),
            confianza=CONFIANZA_DETERMINISTA,
        )
        for ventana in ventanas
    ]


def umbral_adaptativo(niveles_db: Sequence[float]) -> float:
    """Umbral de silencio del video completo.

    Toma el percentil 10 de los niveles (el suelo de ruido del video), le suma 12 dB y acota el
    resultado entre -55 y -35 dBFS. Así un video ruidoso no marca como silencio su ruido de fondo, y un
    video con silencio digital no baja el umbral por debajo de -55 dBFS.
    """
    if not niveles_db:
        return UMBRAL_MINIMO_DB
    suelo = float(np.percentile(np.asarray(niveles_db, dtype=np.float64), PERCENTIL_SUELO))
    return min(max(suelo + MARGEN_SOBRE_SUELO_DB, UMBRAL_MINIMO_DB), UMBRAL_MAXIMO_DB)



def _tramos_consecutivos(puntos: Sequence[PuntoEnergia]) -> list[list[PuntoEnergia]]:
    """Agrupa puntos contiguos. Un hueco de tiempo entre dos puntos los separa."""
    tramos: list[list[PuntoEnergia]] = []
    for punto in puntos:
        if tramos and tramos[-1][-1].fin_ms == punto.inicio_ms:
            tramos[-1].append(punto)
        else:
            tramos.append([punto])
    return tramos


def senales_de_silencio(puntos: Sequence[PuntoEnergia], umbral_db: float) -> list[Senal]:
    senales: list[Senal] = []
    for tramo in _tramos_consecutivos(puntos):
        bajo = [punto for punto in tramo if punto.nivel_db < umbral_db]
        if not bajo:
            continue
        for grupo in _tramos_consecutivos(bajo):
            inicio, fin = grupo[0].inicio_ms, grupo[-1].fin_ms
            if fin - inicio < DURACION_MINIMA_SILENCIO_MS:
                continue
            nivel_medio = sum(punto.nivel_db for punto in grupo) / len(grupo)
            profundidad = _acotar((umbral_db - nivel_medio) / PROFUNDIDAD_SILENCIO_COMPLETA_DB)
            senales.append(
                Senal(
                    tipo=TIPO_SILENCIO,
                    inicio_ms=inicio,
                    fin_ms=fin,
                    valor=profundidad,
                    confianza=CONFIANZA_DETERMINISTA,
                )
            )
    return senales


def senales_de_cambio(puntos: Sequence[PuntoEnergia]) -> list[Senal]:
    senales: list[Senal] = []
    for tramo in _tramos_consecutivos(puntos):
        for anterior, actual in zip(tramo, tramo[1:]):
            salto = abs(actual.nivel_db - anterior.nivel_db)
            if salto < SALTO_MINIMO_DB:
                continue
            senales.append(
                Senal(
                    tipo=TIPO_CAMBIO_INTENSIDAD,
                    inicio_ms=anterior.inicio_ms,
                    fin_ms=actual.fin_ms,
                    valor=_acotar(salto / SALTO_COMPLETO_DB),
                    confianza=CONFIANZA_DETERMINISTA,
                )
            )
    return senales


def consolidar(puntos: Sequence[PuntoEnergia]) -> tuple[Senal, ...]:
    """Silencios y cambios de intensidad calculados con la serie completa del video."""
    umbral = umbral_adaptativo([punto.nivel_db for punto in puntos])
    return tuple(senales_de_silencio(puntos, umbral) + senales_de_cambio(puntos))
