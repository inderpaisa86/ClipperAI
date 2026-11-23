from pathlib import Path

import pytest

from app.plugins.contrato import (
    Analizador,
    ContratoInvalido,
    FotogramaProducido,
    ResultadoSegmento,
    SegmentoEntrada,
    Senal,
)
from app.plugins.registro import AnalizadorNoRegistrado, RegistroAnalizadores


class AnalizadorFalso:
    def __init__(self, identificador: str = "audio", version: str = "1") -> None:
        self._identificador = identificador
        self._version = version

    @property
    def id(self) -> str:
        return self._identificador

    @property
    def version(self) -> str:
        return self._version

    def analizar_segmento(self, segmento, almacen):
        return ResultadoSegmento()


class SinMetodo:
    id = "audio"
    version = "1"


def _senal(**cambios) -> Senal:
    datos = {"tipo": "energia_audio", "inicio_ms": 0, "fin_ms": 1000, "valor": 0.5, "confianza": 0.9}
    datos.update(cambios)
    return Senal(**datos)


def test_senal_valida_se_crea():
    senal = _senal()
    assert senal.inicio_ms == 0 and senal.fin_ms == 1000


def test_senal_de_duracion_cero_es_valida_para_eventos_puntuales():
    assert _senal(inicio_ms=500, fin_ms=500).fin_ms == 500


@pytest.mark.parametrize(
    "cambios",
    [
        {"tipo": "Escena"},
        {"tipo": "escena"},
        {"tipo": "movimiento"},
        {"tipo": "escena-x"},
        {"tipo": ""},
        {"tipo": None},
        {"inicio_ms": -1},
        {"inicio_ms": 1.0},
        {"inicio_ms": True},
        {"fin_ms": 10, "inicio_ms": 20},
        {"valor": 1.01},
        {"valor": -0.01},
        {"valor": float("nan")},
        {"valor": float("inf")},
        {"valor": True},
        {"confianza": "0.5"},
    ],
)
def test_senal_con_datos_fuera_de_contrato_se_rechaza(cambios):
    with pytest.raises(ContratoInvalido):
        _senal(**cambios)


def test_fotograma_producido_exige_tiempo_entero_y_ruta():
    assert FotogramaProducido(tiempo_ms=0, ruta_relativa="work/1/fotogramas/0.jpg").tiempo_ms == 0
    with pytest.raises(ContratoInvalido):
        FotogramaProducido(tiempo_ms=-1, ruta_relativa="work/1/fotogramas/0.jpg")
    with pytest.raises(ContratoInvalido):
        FotogramaProducido(tiempo_ms=1.5, ruta_relativa="work/1/fotogramas/1.jpg")
    with pytest.raises(ContratoInvalido):
        FotogramaProducido(tiempo_ms=1, ruta_relativa="")


def test_segmento_de_entrada_exige_duracion_positiva():
    SegmentoEntrada(ruta_video=Path("video.mp4"), inicio_ms=0, fin_ms=1)
    with pytest.raises(ContratoInvalido):
        SegmentoEntrada(ruta_video=Path("video.mp4"), inicio_ms=5, fin_ms=5)


def test_resultado_vacio_por_defecto():
    resultado = ResultadoSegmento()
    assert resultado.senales == () and resultado.fotogramas == ()


def test_analizador_falso_cumple_el_protocolo():
    assert isinstance(AnalizadorFalso(), Analizador)


def test_objeto_sin_metodo_no_cumple_el_protocolo():
    assert not isinstance(SinMetodo(), Analizador)


def test_registrar_y_obtener_analizador():
    registro = RegistroAnalizadores()
    analizador = AnalizadorFalso("audio", "2")
    registro.registrar(analizador)
    assert registro.obtener("audio") is analizador
    assert registro.existe("audio")
    assert registro.identificadores() == ("audio",)


def test_identificador_duplicado_se_rechaza():
    registro = RegistroAnalizadores()
    registro.registrar(AnalizadorFalso("vision"))
    with pytest.raises(ContratoInvalido):
        registro.registrar(AnalizadorFalso("vision", "9"))


@pytest.mark.parametrize("identificador", ["Audio", "audio-x", "", "1a", "a" * 33])
def test_identificador_no_valido_se_rechaza(identificador):
    with pytest.raises(ContratoInvalido):
        RegistroAnalizadores().registrar(AnalizadorFalso(identificador))


@pytest.mark.parametrize("version", ["", "x" * 33, None])
def test_version_no_valida_se_rechaza(version):
    with pytest.raises(ContratoInvalido):
        RegistroAnalizadores().registrar(AnalizadorFalso("audio", version))


def test_objeto_que_no_cumple_el_contrato_se_rechaza():
    with pytest.raises(ContratoInvalido):
        RegistroAnalizadores().registrar(SinMetodo())


def test_analizador_desconocido_no_se_encuentra():
    registro = RegistroAnalizadores()
    assert not registro.existe("vision")
    with pytest.raises(AnalizadorNoRegistrado):
        registro.obtener("vision")


def test_registros_independientes_no_comparten_analizadores():
    primero, segundo = RegistroAnalizadores(), RegistroAnalizadores()
    primero.registrar(AnalizadorFalso("audio"))
    assert not segundo.existe("audio")
