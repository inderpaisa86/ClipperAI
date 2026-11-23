"""Analizador visual con FFmpeg real y videos sintéticos. Requiere FFmpeg y FFprobe."""
import shutil
import subprocess
from pathlib import Path

import pytest

from app.modules.vision import captura, medidas
from app.modules.vision.analizador import AnalizadorVideo, EstadoPrevioVideo
from app.modules.vision.captura import ErrorVideo
from app.modules.vision.parametros import ParametrosVision
from app.plugins.contrato import FotogramaProducido, SegmentoEntrada
from tests.conftest import requiere_ffmpeg

pytestmark = requiere_ffmpeg

TAMANO = "320x180"


def _ffmpeg() -> Path:
    ruta = shutil.which("ffmpeg")
    assert ruta is not None
    return Path(ruta)


def _video_colores(destino: Path, bloques: list[tuple[str, float]], tamano: str = TAMANO) -> Path:
    """Video formado por colores sólidos consecutivos. Cada bloque es (color, segundos)."""
    comando = ["ffmpeg", "-v", "error", "-y"]
    for color, segundos in bloques:
        comando += ["-f", "lavfi", "-i", f"color=c={color}:s={tamano}:r=30:d={segundos}"]
    entrada = "".join(f"[{i}:v]" for i in range(len(bloques)))
    comando += [
        "-filter_complex", f"{entrada}concat=n={len(bloques)}:v=1:a=0[v]",
        "-map", "[v]", "-c:v", "mpeg4", "-pix_fmt", "yuv420p", str(destino),
    ]
    subprocess.run(comando, check=True, capture_output=True)
    return destino


def _video_caja_en_movimiento(destino: Path, segundos: int = 6) -> Path:
    """Caja blanca de 40 px que se desplaza 20 px por segundo. Cada segundo es un bloque con la caja fija."""
    entradas: list[str] = []
    for i in range(segundos):
        filtro = f"drawbox=x={20 * i}:y=60:w=40:h=40:color=white:t=fill"
        entradas += ["-f", "lavfi", "-i", f"color=c=black:s={TAMANO}:r=30:d=1,{filtro}"]
    entrada = "".join(f"[{i}:v]" for i in range(segundos))
    comando = [
        "ffmpeg", "-v", "error", "-y", *entradas,
        "-filter_complex", f"{entrada}concat=n={segundos}:v=1:a=0[v]",
        "-map", "[v]", "-c:v", "mpeg4", "-pix_fmt", "yuv420p", str(destino),
    ]
    subprocess.run(comando, check=True, capture_output=True)
    return destino


class AlmacenMemoria:
    """Almacén que guarda las miniaturas en memoria, como AlmacenFotogramasVideo pero sin disco."""

    def __init__(self) -> None:
        self.imagenes: dict[int, bytes] = {}

    def guardar(self, tiempo_ms: int, imagen: bytes) -> FotogramaProducido:
        self.imagenes[tiempo_ms] = imagen
        return FotogramaProducido(tiempo_ms=tiempo_ms, ruta_relativa=f"work/1/fotogramas/{tiempo_ms}.jpg")


def _analizador(**parametros) -> AnalizadorVideo:
    return AnalizadorVideo(
        dimensiones_origen=(320, 180),
        ffmpeg=_ffmpeg(),
        parametros=ParametrosVision(**parametros),
    )


def _estado_desde(resultado, almacen: AlmacenMemoria, tiempo_limite: int) -> EstadoPrevioVideo:
    """Estado que dejaría un segmento confirmado antes de `tiempo_limite`, leído como lo hace la tarea."""
    cambios = [s.fin_ms for s in resultado.senales if s.tipo == "cambio_escena" and s.fin_ms < tiempo_limite]
    fotos = [f.tiempo_ms for f in resultado.fotogramas if f.tiempo_ms < tiempo_limite]
    ultimo = max(fotos) if fotos else None
    firma = medidas.firma(medidas.decodificar_jpeg(almacen.imagenes[ultimo])) if ultimo is not None else None
    return EstadoPrevioVideo(
        ultimo_cambio_ms=max(cambios) if cambios else None,
        ultimo_fotograma_ms=ultimo,
        firma_ultimo_fotograma=firma,
    )


# -- Captura de fotogramas ------------------------------------------------------------------

def test_captura_entrega_tiempos_exactos_en_milisegundos(tmp_path):
    video = _video_colores(tmp_path / "v.mp4", [("red", 6)])
    tiempos = [
        (tiempo, imagen.shape)
        for tiempo, imagen in captura.fotogramas_de_rango(
            _ffmpeg(), video, 0, 6000, 1000, 320, 180, 2, lambda: None
        )
    ]
    assert [t for t, _ in tiempos] == [0, 1000, 2000, 3000, 4000, 5000]
    assert all(shape == (180, 320, 3) for _, shape in tiempos)


def test_captura_de_un_segmento_intermedio_usa_la_cuadricula_global(tmp_path):
    video = _video_colores(tmp_path / "v.mp4", [("red", 6)])
    tiempos = [
        t for t, _ in captura.fotogramas_de_rango(
            _ffmpeg(), video, 3000, 6000, 1000, 320, 180, 2, lambda: None
        )
    ]
    assert tiempos == [3000, 4000, 5000]


def test_captura_con_archivo_inexistente_no_expone_la_ruta(tmp_path):
    with pytest.raises(ErrorVideo) as error:
        list(captura.fotogramas_de_rango(
            _ffmpeg(), tmp_path / "no_existe.mp4", 0, 1000, 1000, 320, 180, 2, lambda: None
        ))
    assert str(tmp_path) not in str(error.value)


def test_captura_con_archivo_danado_falla_con_error_claro(tmp_path):
    texto = tmp_path / "danado.mp4"
    texto.write_text("contenido que no es video", encoding="utf-8")
    with pytest.raises(ErrorVideo):
        list(captura.fotogramas_de_rango(
            _ffmpeg(), texto, 0, 1000, 1000, 320, 180, 2, lambda: None
        ))


def test_cancelacion_durante_la_captura_se_propaga(tmp_path):
    class Cancelado(Exception):
        pass

    video = _video_colores(tmp_path / "v.mp4", [("red", 6)])
    contador = {"n": 0}

    def verificar():
        contador["n"] += 1
        if contador["n"] == 2:
            raise Cancelado()

    with pytest.raises(Cancelado):
        list(captura.fotogramas_de_rango(_ffmpeg(), video, 0, 6000, 1000, 320, 180, 2, verificar))


# -- Señales -----------------------------------------------------------------------------------

def test_corte_de_escena_se_registra_como_cambio_escena_en_su_intervalo(tmp_path):
    video = _video_colores(tmp_path / "corte.mp4", [("red", 3), ("blue", 3)])
    resultado = _analizador().analizar_segmento(SegmentoEntrada(video, 0, 6000), AlmacenMemoria())
    cambios = [s for s in resultado.senales if s.tipo == "cambio_escena"]
    assert len(cambios) == 1
    assert cambios[0].inicio_ms <= 3000 <= cambios[0].fin_ms
    assert cambios[0].fin_ms - cambios[0].inicio_ms == 1000
    assert cambios[0].valor > 0.9
    assert cambios[0].confianza == pytest.approx(0.8)


def test_variacion_pequena_de_brillo_no_registra_cambio_de_escena(tmp_path):
    # Gris 128 a gris 140: doce niveles de diferencia, por debajo del umbral de píxel de escena.
    video = _video_colores(tmp_path / "suave.mp4", [("0x808080", 3), ("0x8c8c8c", 3)])
    resultado = _analizador().analizar_segmento(SegmentoEntrada(video, 0, 6000), AlmacenMemoria())
    assert [s for s in resultado.senales if s.tipo == "cambio_escena"] == []
    brillos = [s.valor for s in resultado.senales if s.tipo == "brillo"]
    assert brillos[-1] > brillos[0]


def test_brillo_se_normaliza_entre_negro_y_blanco(tmp_path):
    video = _video_colores(tmp_path / "bn.mp4", [("black", 2), ("white", 2)])
    resultado = _analizador().analizar_segmento(SegmentoEntrada(video, 0, 4000), AlmacenMemoria())
    brillos = [s for s in resultado.senales if s.tipo == "brillo"]
    assert brillos[0].valor < 0.02
    assert brillos[-1].valor > 0.98
    assert all(0.0 <= s.valor <= 1.0 and s.confianza == 1.0 for s in brillos)


def test_movimiento_pequeno_se_mide_normalizado_y_queda_bajo_el_umbral_de_escena(tmp_path):
    video = _video_caja_en_movimiento(tmp_path / "caja.mp4")
    resultado = _analizador().analizar_segmento(SegmentoEntrada(video, 0, 5000), AlmacenMemoria())
    movimientos = [s.valor for s in resultado.senales if s.tipo == "movimiento"]
    assert any(valor > 0 for valor in movimientos)
    assert all(0.0 <= valor <= 1.0 for valor in movimientos)
    assert max(movimientos) < 0.2
    assert [s for s in resultado.senales if s.tipo == "cambio_escena"] == []


def test_no_hay_muestras_de_movimiento_duplicadas_ni_solapadas(tmp_path):
    video = _video_colores(tmp_path / "v.mp4", [("red", 2), ("blue", 2)])
    resultado = _analizador().analizar_segmento(SegmentoEntrada(video, 0, 4000), AlmacenMemoria())
    intervalos = [(s.inicio_ms, s.fin_ms) for s in resultado.senales if s.tipo == "movimiento"]
    assert intervalos == [(0, 1000), (1000, 2000), (2000, 3000)]


# -- Segmentos consecutivos ---------------------------------------------------------------------

def test_segmentos_consecutivos_producen_las_mismas_senales_que_un_analisis_unico(tmp_path):
    video = _video_colores(tmp_path / "v.mp4", [("red", 3), ("blue", 3), ("green", 2)])
    completo = _analizador().analizar_segmento(SegmentoEntrada(video, 0, 8000), AlmacenMemoria())

    almacen = AlmacenMemoria()
    primero = _analizador().analizar_segmento(SegmentoEntrada(video, 0, 4000), almacen)
    estado = _estado_desde(primero, almacen, 4000)
    segundo = _analizador().analizar_segmento(SegmentoEntrada(video, 4000, 8000), almacen, estado)

    def claves(resultado):
        return sorted((s.tipo, s.inicio_ms, s.fin_ms, round(s.valor, 6)) for s in resultado.senales)

    unidos = list(claves(primero)) + list(claves(segundo))
    assert len(unidos) == len(set(unidos))
    assert sorted(unidos) == claves(completo)


def test_la_distancia_minima_entre_cortes_se_respeta_a_traves_del_borde_del_segmento(tmp_path):
    # Dos cortes con un segundo de diferencia, justo en el borde del segmento [4000, 8000).
    video = _video_colores(tmp_path / "borde.mp4", [("red", 3), ("blue", 1), ("green", 4)])
    completo = _analizador().analizar_segmento(SegmentoEntrada(video, 0, 8000), AlmacenMemoria())
    cortes_completo = [s.fin_ms for s in completo.senales if s.tipo == "cambio_escena"]
    assert cortes_completo == [3000]

    almacen = AlmacenMemoria()
    primero = _analizador().analizar_segmento(SegmentoEntrada(video, 0, 4000), almacen)
    segundo_sin_estado = _analizador().analizar_segmento(SegmentoEntrada(video, 4000, 8000), AlmacenMemoria())
    assert [s.fin_ms for s in segundo_sin_estado.senales if s.tipo == "cambio_escena"] == [4000]

    estado = _estado_desde(primero, almacen, 4000)
    segundo = _analizador().analizar_segmento(SegmentoEntrada(video, 4000, 8000), almacen, estado)
    assert [s.fin_ms for s in segundo.senales if s.tipo == "cambio_escena"] == []


def test_fotogramas_representativos_son_jpeg_de_ancho_fijo_y_sin_repetir_tiempo(tmp_path):
    video = _video_colores(tmp_path / "v.mp4", [("red", 2), ("blue", 2), ("green", 2)])
    almacen = AlmacenMemoria()
    resultado = _analizador(maximo_fotogramas_por_minuto=60, separacion_minima_fotogramas_ms=500).analizar_segmento(
        SegmentoEntrada(video, 0, 6000), almacen
    )
    tiempos = [f.tiempo_ms for f in resultado.fotogramas]
    assert len(tiempos) == len(set(tiempos)) >= 2
    for tiempo in tiempos:
        imagen = medidas.decodificar_jpeg(almacen.imagenes[tiempo])
        assert imagen.shape[1] == 320 and imagen.shape[0] == 180


def test_el_limite_de_fotogramas_por_segmento_se_respeta(tmp_path):
    video = _video_colores(tmp_path / "v.mp4", [("red", 1), ("blue", 1), ("green", 1), ("black", 1), ("white", 1)])
    resultado = _analizador(maximo_fotogramas_por_minuto=6, separacion_minima_fotogramas_ms=500).analizar_segmento(
        SegmentoEntrada(video, 0, 5000), AlmacenMemoria()
    )
    # Un segmento de cinco segundos admite como máximo round(6 * 5000 / 60000) = 1 fotograma, al menos uno.
    assert len(resultado.fotogramas) == 1


def test_video_sin_muestras_suficientes_falla_y_no_guarda_nada(tmp_path):
    video = _video_colores(tmp_path / "corto.mp4", [("red", 1)])
    almacen = AlmacenMemoria()
    with pytest.raises(ErrorVideo):
        _analizador().analizar_segmento(SegmentoEntrada(video, 0, 20_000), almacen)
    assert almacen.imagenes == {}
