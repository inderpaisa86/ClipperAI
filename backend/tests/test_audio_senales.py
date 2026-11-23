"""Analizador de audio con datos sintéticos: energía, vocabulario, silencios y cambios. Sin FFmpeg."""

import io

import numpy as np
import pytest

from app.composicion import registrar
from app.modules.audio import analizador, energia
from app.modules.audio.energia import (
    BYTES_POR_VENTANA,
    VentanaEnergia,
    db_desde_rms,
    db_desde_valor,
    valor_desde_db,
    ventanas_de_flujo,
)
from app.modules.audio.senales import (
    PuntoEnergia,
    TIPOS_AUDIO,
    consolidar,
    senales_de_cambio,
    senales_de_energia,
    senales_de_silencio,
    umbral_adaptativo,
)
from app.plugins.contrato import Senal
from app.plugins.registro import REGISTRO


def _pcm(muestras: np.ndarray) -> bytes:
    return muestras.astype("<i2").tobytes()


def _tono(segundos: float, amplitud: float) -> np.ndarray:
    tiempo = np.arange(int(16000 * segundos)) / 16000
    return (amplitud * 32767 * np.sin(2 * np.pi * 440 * tiempo)).astype(np.int16)


def _silencio(segundos: float) -> np.ndarray:
    return np.zeros(int(16000 * segundos), dtype=np.int16)


def _puntos(niveles_db: list[float]) -> list[PuntoEnergia]:
    return [
        PuntoEnergia(inicio_ms=i * 200, fin_ms=i * 200 + 200, nivel_db=nivel)
        for i, nivel in enumerate(niveles_db)
    ]


# -- Energía RMS ----------------------------------------------------------------


def test_rms_de_un_tono_coincide_con_su_amplitud_teorica():
    flujo = io.BytesIO(_pcm(_tono(1.0, amplitud=0.5)))
    ventanas = list(ventanas_de_flujo(flujo, 0, lambda: None))
    assert len(ventanas) == 5
    assert ventanas[0].rms == pytest.approx(0.5 / np.sqrt(2), rel=0.01)


def test_ventanas_son_de_200_ms_con_tiempos_enteros_desplazados():
    flujo = io.BytesIO(_pcm(_tono(0.6, amplitud=0.2)))
    ventanas = list(ventanas_de_flujo(flujo, 60_000, lambda: None))
    assert [v.inicio_ms for v in ventanas] == [60_000, 60_200, 60_400]
    assert all(isinstance(v.inicio_ms, int) for v in ventanas)


def test_cola_menor_de_una_ventana_se_descarta():
    datos = _pcm(_tono(0.5, amplitud=0.2)) + b"\x01" * (BYTES_POR_VENTANA - 10)
    ventanas = list(ventanas_de_flujo(io.BytesIO(datos), 0, lambda: None))
    # 16000 bytes de tono + 6390 de cola: tres ventanas completas, y los 3190 bytes restantes se descartan.
    assert len(ventanas) == 3


def test_verificar_se_llama_por_ventana_y_puede_cancelar():
    llamadas = []

    class Cancelado(Exception):
        pass

    def verificar():
        llamadas.append(1)
        if len(llamadas) == 3:
            raise Cancelado()

    with pytest.raises(Cancelado):
        list(ventanas_de_flujo(io.BytesIO(_pcm(_tono(2.0, 0.2))), 0, verificar))
    assert len(llamadas) == 3


def test_silencio_digital_tiene_nivel_suelo_y_valor_cero():
    assert db_desde_rms(0.0) == energia.SUELO_DB
    assert valor_desde_db(energia.SUELO_DB) == 0.0
    assert valor_desde_db(0.0) == 1.0


def test_valor_normalizado_es_invertible():
    for nivel in (-90.0, -60.0, -33.3, -12.0, 0.0):
        assert db_desde_valor(valor_desde_db(nivel)) == pytest.approx(nivel)


# -- Vocabulario y contrato -------------------------------------------------------


def test_vocabulario_de_audio_cumple_el_patron_del_contrato():
    for tipo in TIPOS_AUDIO:
        Senal(tipo=tipo, inicio_ms=0, fin_ms=200, valor=0.5, confianza=1.0)
    assert TIPOS_AUDIO == ("energia_audio", "silencio", "cambio_intensidad")


def test_senales_de_energia_tienen_intervalos_enteros_de_200_ms():
    ventanas = [VentanaEnergia(inicio_ms=400, rms=0.1), VentanaEnergia(inicio_ms=600, rms=0.0)]
    generadas = senales_de_energia(ventanas)
    assert [(s.inicio_ms, s.fin_ms) for s in generadas] == [(400, 600), (600, 800)]
    assert all(s.tipo == "energia_audio" for s in generadas)
    assert generadas[1].valor == 0.0


def test_analizador_registrado_con_id_y_version_del_contrato():
    registrar()
    registrar()  # Idempotente.
    assert REGISTRO.existe("audio")
    adaptador = REGISTRO.obtener("audio")
    assert adaptador.id == analizador.IDENTIFICADOR == "audio"
    assert adaptador.version == analizador.VERSION
    assert 0 < len(adaptador.version) <= 32


# -- Umbral, silencios y cambios ---------------------------------------------------


def test_umbral_adaptativo_se_acota_entre_menos_55_y_menos_35_db():
    assert umbral_adaptativo([-20.0] * 50) == -35.0
    assert umbral_adaptativo([-90.0] * 50) == -55.0
    assert umbral_adaptativo([-70.0] * 10 + [-20.0] * 40) == pytest.approx(-55.0)
    assert umbral_adaptativo([]) == -55.0


def test_silencio_detectado_entre_dos_tramos_de_voz():
    niveles = [-20.0] * 25 + [-90.0] * 25 + [-20.0] * 25
    puntos = _puntos(niveles)
    umbral = umbral_adaptativo(niveles)
    silencios = senales_de_silencio(puntos, umbral)
    assert [(s.inicio_ms, s.fin_ms) for s in silencios] == [(5000, 10000)]
    assert silencios[0].valor == 1.0
    assert silencios[0].confianza == 1.0


def test_silencio_mas_corto_que_el_minimo_se_ignora():
    niveles = [-20.0] * 10 + [-90.0] * 1 + [-20.0] * 10
    assert senales_de_silencio(_puntos(niveles), -55.0) == []


def test_silencio_de_400_ms_no_alcanza_el_minimo_de_500():
    niveles = [-20.0] * 10 + [-90.0] * 2 + [-20.0] * 10
    assert senales_de_silencio(_puntos(niveles), -55.0) == []


def test_silencio_de_600_ms_supera_el_minimo_y_se_reporta():
    # Las ventanas son de 200 ms, así que la duración mínima de 500 ms se alcanza con 600 ms.
    niveles = [-20.0] * 10 + [-90.0] * 3 + [-20.0] * 10
    silencios = senales_de_silencio(_puntos(niveles), -55.0)
    assert [(s.inicio_ms, s.fin_ms) for s in silencios] == [(2000, 2600)]


def test_huecos_de_tiempo_separan_los_tramos():
    puntos = [
        PuntoEnergia(0, 200, -90.0),
        PuntoEnergia(200, 400, -90.0),
        PuntoEnergia(400, 600, -90.0),
        PuntoEnergia(1000, 1200, -90.0),
        PuntoEnergia(1200, 1400, -90.0),
        PuntoEnergia(1400, 1600, -90.0),
    ]
    silencios = senales_de_silencio(puntos, -55.0)
    assert [(s.inicio_ms, s.fin_ms) for s in silencios] == [(0, 600), (1000, 1600)]


def test_umbral_es_percentil_10_mas_12_db():
    # 20 % de ventanas en -70 dB: P10 = -70, umbral = -58, acotado a -55.
    niveles = [-70.0] * 20 + [-20.0] * 80
    assert umbral_adaptativo(niveles) == -55.0
    # P10 = -45 dB: -45 + 12 = -33 y se acota a -35.
    niveles = [-45.0] * 100
    assert umbral_adaptativo(niveles) == -35.0
    # P10 = -50 dB: -50 + 12 = -38, dentro de los límites.
    niveles = [-50.0] * 100
    assert umbral_adaptativo(niveles) == pytest.approx(-38.0)


def test_silencio_en_el_limite_entre_segmentos_se_une_con_el_resto_del_video():
    """Un silencio que cruza el límite de 60 s entre dos segmentos debe salir como una sola señal."""
    primer_segmento = [PuntoEnergia(59_000 + i * 200, 59_200 + i * 200, -90.0) for i in range(5)]
    segundo_segmento = [PuntoEnergia(60_000 + i * 200, 60_200 + i * 200, -90.0) for i in range(5)]
    resultado = consolidar(primer_segmento + segundo_segmento)
    silencios = [s for s in resultado if s.tipo == "silencio"]
    assert [(s.inicio_ms, s.fin_ms) for s in silencios] == [(59_000, 61_000)]


def test_cambio_en_el_limite_entre_segmentos_se_detecta():
    antes = [PuntoEnergia(59_800, 60_000, -20.0)]
    despues = [PuntoEnergia(60_000, 60_200, -90.0)]
    cambios = senales_de_cambio(antes + despues)
    assert [(c.inicio_ms, c.fin_ms) for c in cambios] == [(59_800, 60_200)]


def test_cambio_de_intensidad_marca_las_dos_ventanas_del_salto():
    puntos = _puntos([-20.0, -20.0, -90.0, -90.0, -20.0])
    cambios = senales_de_cambio(puntos)
    assert [(c.inicio_ms, c.fin_ms) for c in cambios] == [(200, 600), (600, 1000)]
    assert all(c.tipo == "cambio_intensidad" for c in cambios)
    assert all(c.valor == 1.0 for c in cambios)


def test_cambio_pequeno_no_genera_senal():
    assert senales_de_cambio(_puntos([-30.0, -35.0, -40.0])) == []


def test_consolidar_devuelve_solo_silencios_y_cambios_con_enteros():
    niveles = [-20.0] * 25 + [-90.0] * 25 + [-20.0] * 25
    resultado = consolidar(_puntos(niveles))
    tipos = {senal.tipo for senal in resultado}
    assert tipos == {"silencio", "cambio_intensidad"}
    for senal in resultado:
        assert isinstance(senal.inicio_ms, int) and isinstance(senal.fin_ms, int)
        assert 0.0 <= senal.valor <= 1.0
        assert 0.0 <= senal.confianza <= 1.0


def test_consolidar_sin_puntos_no_devuelve_nada():
    assert consolidar([]) == ()


def test_planificacion_de_segmentos_cubre_el_video_sin_huecos():
    from app.modules.audio.service import TIPO_SEGMENTO_CONSOLIDACION, TIPO_SEGMENTO_ENERGIA, planificar_segmentos

    segmentos = planificar_segmentos(150_300)
    energia_segmentos = [s for s in segmentos if s[0] == TIPO_SEGMENTO_ENERGIA]
    assert [(s[2], s[3]) for s in energia_segmentos] == [(0, 60_000), (60_000, 120_000), (120_000, 150_300)]
    assert [s[1] for s in energia_segmentos] == [0, 1, 2]
    assert segmentos[-1] == (TIPO_SEGMENTO_CONSOLIDACION, 0, 0, 150_300)


def test_segmentos_de_energia_empiezan_en_multiplos_de_la_ventana():
    from app.modules.audio.service import DURACION_SEGMENTO_MS, planificar_segmentos

    assert DURACION_SEGMENTO_MS % energia.VENTANA_MS == 0
    for tipo, _, inicio, _ in planificar_segmentos(300_000):
        if tipo == "energia":
            assert inicio % energia.VENTANA_MS == 0
