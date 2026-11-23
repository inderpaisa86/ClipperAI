"""Medidas, selección de fotogramas y parámetros del analizador visual. No necesitan FFmpeg."""
import numpy as np
import pytest

from app.modules.vision import medidas
from app.modules.vision.captura import ErrorVideo
from app.modules.vision.parametros import PARAMETROS_POR_DEFECTO, ParametrosVision, dimensiones_proporcionales
from app.modules.vision.seleccion import CandidatoFotograma, limite_del_segmento, seleccionar
from app.modules.vision.service import TIPO_SEGMENTO_CIERRE, TIPO_SEGMENTO_FOTOGRAMAS, planificar_segmentos


def _gris(valor: int, ancho: int = 160, alto: int = 90) -> np.ndarray:
    return np.full((alto, ancho), valor, dtype=np.uint8)


def _imagen_bgr(valor: int, ancho: int = 320, alto: int = 180) -> np.ndarray:
    return np.full((alto, ancho, 3), valor, dtype=np.uint8)


# -- Brillo -------------------------------------------------------------------------------

def test_brillo_se_normaliza_entre_cero_y_uno():
    assert medidas.brillo(_gris(0)) == 0.0
    assert medidas.brillo(_gris(255)) == 1.0
    assert medidas.brillo(_gris(128)) == pytest.approx(128 / 255)


# -- Cambios entre fotogramas -----------------------------------------------------------

def test_ruido_de_compresion_no_cuenta_como_movimiento_ni_escena():
    rng = np.random.default_rng(7)
    base = _gris(120)
    ruido = np.clip(base.astype(int) + rng.integers(-3, 4, size=base.shape), 0, 255).astype(np.uint8)
    escena, movimiento = medidas.fracciones_cambiadas(base, ruido, 30, 20)
    assert escena == 0.0
    assert movimiento == 0.0


def test_variacion_global_de_iluminacion_pequena_no_es_cambio_de_escena():
    escena, movimiento = medidas.fracciones_cambiadas(_gris(100), _gris(112), 30, 20)
    assert escena == 0.0
    assert movimiento == 0.0


def test_cambio_total_de_contenido_da_fraccion_uno():
    escena, movimiento = medidas.fracciones_cambiadas(_gris(0), _gris(255), 30, 20)
    assert escena == 1.0
    assert movimiento == 1.0


def test_bloque_pequeno_en_movimiento_queda_por_debajo_del_umbral_de_escena():
    antes = _gris(40)
    despues = _gris(40)
    despues[:, :16] = 220  # aproximadamente el 10 % de la imagen
    escena, movimiento = medidas.fracciones_cambiadas(antes, despues, 30, 20)
    assert 0.0 < movimiento < 0.2
    assert escena == pytest.approx(movimiento)
    assert escena < PARAMETROS_POR_DEFECTO.umbral_fraccion_escena


def test_las_fracciones_estan_normalizadas():
    rng = np.random.default_rng(3)
    a = rng.integers(0, 256, size=(90, 160), dtype=np.uint8)
    b = rng.integers(0, 256, size=(90, 160), dtype=np.uint8)
    for valor in medidas.fracciones_cambiadas(a, b, 30, 20):
        assert 0.0 <= valor <= 1.0


# -- Firma visual -----------------------------------------------------------------------

def test_firma_de_imagenes_iguales_tiene_distancia_cero():
    imagen = _imagen_bgr(90)
    assert medidas.distancia_firmas(medidas.firma(imagen), medidas.firma(imagen.copy())) == 0.0


def test_firma_distingue_imagenes_muy_distintas():
    distancia = medidas.distancia_firmas(medidas.firma(_imagen_bgr(0)), medidas.firma(_imagen_bgr(255)))
    assert distancia == pytest.approx(1.0)


def test_miniatura_no_jpeg_no_se_puede_decodificar():
    with pytest.raises(ErrorVideo):
        medidas.decodificar_jpeg(b"no es una imagen")


# -- Dimensiones y parámetros -----------------------------------------------------------

@pytest.mark.parametrize(
    ("origen", "maximo", "esperado"),
    [
        ((1920, 1080), 320, (320, 180)),
        ((1080, 1920), 320, (320, 568)),
        ((160, 90), 320, (160, 90)),
        ((321, 181), 320, (320, 180)),
    ],
)
def test_dimensiones_conservan_la_relacion_de_aspecto_sin_ampliar(origen, maximo, esperado):
    ancho, alto = dimensiones_proporcionales(origen[0], origen[1], maximo)
    assert (ancho, alto) == esperado
    assert ancho % 2 == 0 and alto % 2 == 0
    assert abs(ancho / alto - origen[0] / origen[1]) < 0.02


def test_parametros_invalidos_se_rechazan():
    with pytest.raises(ValueError):
        ParametrosVision(umbral_fraccion_escena=1.5)
    with pytest.raises(ValueError):
        ParametrosVision(intervalo_muestreo_ms=0)
    with pytest.raises(ValueError):
        ParametrosVision(ancho_fotograma=100, ancho_analisis=160)


def test_limite_de_fotogramas_es_proporcional_a_la_duracion_del_segmento():
    assert limite_del_segmento(PARAMETROS_POR_DEFECTO, 60_000) == 6
    assert limite_del_segmento(PARAMETROS_POR_DEFECTO, 30_000) == 3
    assert limite_del_segmento(PARAMETROS_POR_DEFECTO, 1_000) == 1


def test_planificacion_de_segmentos_cubre_el_video_sin_huecos():
    segmentos = planificar_segmentos(130_000, 60_000)
    fotogramas = [s for s in segmentos if s[0] == TIPO_SEGMENTO_FOTOGRAMAS]
    assert [(indice, inicio, fin) for _, indice, inicio, fin in fotogramas] == [
        (0, 0, 60_000),
        (1, 60_000, 120_000),
        (2, 120_000, 130_000),
    ]
    assert segmentos[-1] == (TIPO_SEGMENTO_CIERRE, 0, 0, 130_000)


# -- Selección de fotogramas --------------------------------------------------------------

def _candidato(tiempo: int, puntuacion: float, semilla: int) -> CandidatoFotograma:
    imagen = _imagen_bgr(semilla * 40 % 256)
    return CandidatoFotograma(
        tiempo_ms=tiempo,
        puntuacion=puntuacion,
        imagen=imagen,
        firma=medidas.firma(imagen),
    )


def test_seleccion_respeta_el_maximo():
    candidatos = [_candidato(t * 10_000, 1.0, t) for t in range(8)]
    elegidos = seleccionar(candidatos, PARAMETROS_POR_DEFECTO, 3, None)
    assert len(elegidos) == 3


def test_seleccion_descarta_fotogramas_demasiado_cercanos_en_el_tiempo():
    candidatos = [_candidato(10_000, 1.0, 1), _candidato(12_000, 0.9, 2), _candidato(20_000, 0.8, 3)]
    elegidos = seleccionar(candidatos, PARAMETROS_POR_DEFECTO, 6, None)
    assert [c.tiempo_ms for c in elegidos] == [10_000, 20_000]


def test_seleccion_descarta_fotogramas_visualmente_repetidos():
    casi_igual = _candidato(40_000, 0.5, 1)
    original = _candidato(10_000, 1.0, 1)
    otro = _candidato(30_000, 0.6, 9)
    elegidos = seleccionar([original, casi_igual, otro], PARAMETROS_POR_DEFECTO, 6, None)
    assert [c.tiempo_ms for c in elegidos] == [10_000, 30_000]


def test_seleccion_considera_el_ultimo_fotograma_del_segmento_anterior():
    candidato = _candidato(61_000, 1.0, 4)
    cercano = (58_000, candidato.firma)
    assert seleccionar([candidato], PARAMETROS_POR_DEFECTO, 6, cercano) == []
    lejano = (10_000, _candidato(0, 0, 5).firma)
    assert [c.tiempo_ms for c in seleccionar([candidato], PARAMETROS_POR_DEFECTO, 6, lejano)] == [61_000]
