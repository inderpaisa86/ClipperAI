"""Confirmación de segmentos con resultados de análisis dentro de una sola transacción."""

from pathlib import Path

import pytest

from app.core.rutas import RaizDatos
from app.db.conexion import conectar
from app.db.migraciones import aplicar_migraciones
from app.jobs import service as trabajos
from app.jobs.service import ReclamoPerdido, TrabajoCancelado
from app.modules.analisis import service as analisis
from app.plugins.contrato import ResultadoSegmento, Senal
from tests.ayudas import JPEG_PRUEBA, AnalizadorFalso, insertar_video_directo, registro_con

TOKEN = "t" * 32


@pytest.fixture
def base(tmp_path: Path):
    conexion = conectar(tmp_path / "datos" / "clipperai.db")
    aplicar_migraciones(conexion)
    raiz = RaizDatos(tmp_path / "datos")
    proyecto = conexion.execute("INSERT INTO proyectos (nombre) VALUES ('p')").lastrowid
    conexion.commit()
    video = insertar_video_directo(conexion, proyecto)
    analisis_id = analisis.preparar_analisis(conexion, video, "audio", registro_con(AnalizadorFalso("audio"))).id
    yield conexion, raiz, video, analisis_id
    conexion.close()


def _resultado(raiz: RaizDatos, video: int) -> ResultadoSegmento:
    senal = Senal(tipo="energia_audio", inicio_ms=0, fin_ms=1000, valor=0.4, confianza=0.9)
    return ResultadoSegmento(senales=(senal,))


def _trabajo_con_segmento_en_proceso(conexion, token: str = TOKEN) -> int:
    trabajo = trabajos.crear(conexion, "diagnostico_espera", {}, [("audio", 0, 0, 1000)])
    assert trabajos.reclamar_siguiente(conexion, token) == trabajo
    assert trabajos.marcar_segmento_procesando(conexion, trabajo, token, "audio", 0) is True
    return trabajo


def _senales(conexion, analisis_id: int) -> int:
    return conexion.execute("SELECT COUNT(*) FROM senales WHERE analisis_id = ?", (analisis_id,)).fetchone()[0]


def _estado_segmento(conexion, trabajo: int) -> str:
    return conexion.execute(
        "SELECT estado FROM segmentos_trabajo WHERE trabajo_id = ? AND indice = 0", (trabajo,)
    ).fetchone()["estado"]


def test_confirmar_segmento_guarda_senales_y_marca_completado(base):
    conexion, raiz, video, analisis_id = base
    trabajo = _trabajo_con_segmento_en_proceso(conexion)
    resultado = _resultado(raiz, video)

    confirmado = trabajos.confirmar_segmento(
        conexion, trabajo, TOKEN, "audio", 0, None, None, "1",
        persistir=lambda c: analisis.persistir_resultado(c, raiz, analisis_id, resultado),
    )

    assert confirmado is True
    assert _senales(conexion, analisis_id) == 1
    assert _estado_segmento(conexion, trabajo) == "completado"


def test_si_persistir_falla_no_queda_ni_la_senal_ni_el_segmento_completado(base):
    conexion, raiz, video, analisis_id = base
    trabajo = _trabajo_con_segmento_en_proceso(conexion)

    def persistir_con_fallo(c):
        analisis.persistir_resultado(c, raiz, analisis_id, _resultado(raiz, video))
        raise RuntimeError("fallo simulado al escribir")

    with pytest.raises(RuntimeError):
        trabajos.confirmar_segmento(
            conexion, trabajo, TOKEN, "audio", 0, None, None, "1", persistir=persistir_con_fallo
        )

    assert _senales(conexion, analisis_id) == 0
    assert _estado_segmento(conexion, trabajo) == "procesando"


def test_un_token_ajeno_no_escribe_resultados(base):
    conexion, raiz, video, analisis_id = base
    trabajo = _trabajo_con_segmento_en_proceso(conexion)
    llamadas = []
    with pytest.raises(ReclamoPerdido):
        trabajos.confirmar_segmento(
            conexion, trabajo, "otro" * 8, "audio", 0, None, None, "1",
            persistir=lambda c: llamadas.append(c),
        )
    assert llamadas == []
    assert _senales(conexion, analisis_id) == 0


def test_un_trabajo_cancelado_no_escribe_resultados(base):
    conexion, raiz, video, analisis_id = base
    trabajo = _trabajo_con_segmento_en_proceso(conexion)
    trabajos.cancelar(conexion, trabajo)
    with pytest.raises(TrabajoCancelado):
        trabajos.confirmar_segmento(
            conexion, trabajo, TOKEN, "audio", 0, None, None, "1",
            persistir=lambda c: analisis.persistir_resultado(c, raiz, analisis_id, _resultado(raiz, video)),
        )
    assert _senales(conexion, analisis_id) == 0


def test_un_segmento_ya_confirmado_no_vuelve_a_persistir(base):
    conexion, raiz, video, analisis_id = base
    trabajo = _trabajo_con_segmento_en_proceso(conexion)
    llamadas = []

    def persistir(c):
        llamadas.append(1)
        analisis.persistir_resultado(c, raiz, analisis_id, _resultado(raiz, video))

    assert trabajos.confirmar_segmento(conexion, trabajo, TOKEN, "audio", 0, None, None, "1", persistir=persistir)
    assert trabajos.confirmar_segmento(conexion, trabajo, TOKEN, "audio", 0, None, None, "1", persistir=persistir) is False
    assert len(llamadas) == 1
    assert _senales(conexion, analisis_id) == 1


def test_confirmar_sin_persistir_sigue_funcionando(base):
    conexion, _, _, _ = base
    trabajo = _trabajo_con_segmento_en_proceso(conexion)
    assert trabajos.confirmar_segmento(conexion, trabajo, TOKEN, "audio", 0, None, None, None) is True
    assert _estado_segmento(conexion, trabajo) == "completado"


def test_hay_trabajo_ejecutandose_refleja_el_reclamo(base):
    conexion, _, _, _ = base
    assert trabajos.hay_trabajo_ejecutandose(conexion) is False
    _trabajo_con_segmento_en_proceso(conexion)
    assert trabajos.hay_trabajo_ejecutandose(conexion) is True


def test_miniatura_escrita_antes_de_confirmar_queda_registrada_en_la_misma_transaccion(base):
    conexion, raiz, video, analisis_id = base
    trabajo = _trabajo_con_segmento_en_proceso(conexion)
    from app.modules.analisis.almacenamiento import AlmacenFotogramasVideo

    fotograma = AlmacenFotogramasVideo(raiz, video).guardar(1000, JPEG_PRUEBA)
    resultado = ResultadoSegmento(senales=(), fotogramas=(fotograma,))
    trabajos.confirmar_segmento(
        conexion, trabajo, TOKEN, "audio", 0, None, None, "1",
        persistir=lambda c: analisis.persistir_resultado(c, raiz, analisis_id, resultado),
    )
    assert analisis.listar_fotogramas(conexion, video, "audio")[0].tiempo_ms == 1000
