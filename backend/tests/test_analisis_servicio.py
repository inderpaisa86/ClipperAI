from pathlib import Path

import pytest

from app.core.errores import Conflicto, NoEncontrado, SolicitudInvalida
from app.core.rutas import RaizDatos
from app.db.conexion import conectar
from app.db.migraciones import aplicar_migraciones
from app.modules.analisis import service
from app.modules.analisis.almacenamiento import AlmacenFotogramasVideo
from app.plugins.contrato import FotogramaProducido, ContratoInvalido, ResultadoSegmento, Senal
from app.plugins.registro import RegistroAnalizadores
from tests.ayudas import JPEG_PRUEBA, AnalizadorFalso, insertar_video_directo, persistir_en_transaccion, registro_con


@pytest.fixture
def base(tmp_path: Path):
    conexion = conectar(tmp_path / "datos" / "clipperai.db")
    aplicar_migraciones(conexion)
    raiz = RaizDatos(tmp_path / "datos")
    yield conexion, raiz
    conexion.close()


def _video(conexion) -> int:
    proyecto = conexion.execute("INSERT INTO proyectos (nombre) VALUES ('p')").lastrowid
    conexion.commit()
    return insertar_video_directo(conexion, proyecto)


def _senal(tipo: str = "silencio", inicio: int = 0, fin: int = 1000) -> Senal:
    return Senal(tipo=tipo, inicio_ms=inicio, fin_ms=fin, valor=0.5, confianza=0.8)


def _conteo(conexion, tabla: str, analisis_id: int) -> int:
    columna = "analisis_id"
    return conexion.execute(f"SELECT COUNT(*) FROM {tabla} WHERE {columna} = ?", (analisis_id,)).fetchone()[0]


def _miniatura(raiz: RaizDatos, video_id: int, tiempo: int) -> FotogramaProducido:
    return AlmacenFotogramasVideo(raiz, video_id).guardar(tiempo, JPEG_PRUEBA)


# -- Preparación del análisis ---------------------------------------------

def test_preparar_crea_un_analisis_pendiente(base):
    conexion, _ = base
    video = _video(conexion)
    analisis = service.preparar_analisis(conexion, video, "audio", registro_con(AnalizadorFalso("audio", "3")))
    assert analisis.estado == "pendiente"
    assert analisis.version_analizador == "3"
    assert analisis.analizador == "audio"
    assert analisis.video_id == video


def test_preparar_con_la_misma_version_completada_no_cambia_nada(base):
    conexion, raiz = base
    video = _video(conexion)
    registro = registro_con(AnalizadorFalso("audio", "1"))
    primero = service.preparar_analisis(conexion, video, "audio", registro)
    persistir_en_transaccion(conexion, raiz, primero.id, ResultadoSegmento(senales=(_senal(),)))
    service.marcar_estado(conexion, primero.id, "completado")

    segundo = service.preparar_analisis(conexion, video, "audio", registro)

    assert segundo.id == primero.id and segundo.estado == "completado"
    assert _conteo(conexion, "senales", primero.id) == 1


def test_preparar_con_otra_version_invalida_los_resultados(base):
    conexion, raiz = base
    video = _video(conexion)
    primero = service.preparar_analisis(conexion, video, "audio", registro_con(AnalizadorFalso("audio", "1")))
    persistir_en_transaccion(
        conexion,
        raiz,
        primero.id,
        ResultadoSegmento(
            senales=(_senal(),),
            fotogramas=(_miniatura(raiz, video, 1000),),
        ),
    )
    service.marcar_estado(conexion, primero.id, "completado")

    nuevo = service.preparar_analisis(conexion, video, "audio", registro_con(AnalizadorFalso("audio", "2")))

    assert nuevo.id == primero.id
    assert nuevo.version_analizador == "2"
    assert nuevo.estado == "pendiente"
    assert _conteo(conexion, "senales", primero.id) == 0
    assert _conteo(conexion, "fotogramas", primero.id) == 0


def test_preparar_con_analisis_en_curso_es_conflicto(base):
    conexion, _ = base
    video = _video(conexion)
    registro = registro_con(AnalizadorFalso("audio"))
    analisis = service.preparar_analisis(conexion, video, "audio", registro)
    service.marcar_estado(conexion, analisis.id, "en_curso")
    with pytest.raises(Conflicto):
        service.preparar_analisis(conexion, video, "audio", registro)


def test_preparar_fallido_vuelve_a_pendiente_y_conserva_resultados_de_la_misma_version(base):
    conexion, raiz = base
    video = _video(conexion)
    registro = registro_con(AnalizadorFalso("audio", "1"))
    analisis = service.preparar_analisis(conexion, video, "audio", registro)
    persistir_en_transaccion(conexion, raiz, analisis.id, ResultadoSegmento(senales=(_senal(),)))
    service.marcar_estado(conexion, analisis.id, "fallido", error="Fallo de prueba")

    reintento = service.preparar_analisis(conexion, video, "audio", registro)

    assert reintento.estado == "pendiente"
    assert reintento.error is None
    assert _conteo(conexion, "senales", analisis.id) == 1


def test_preparar_con_analizador_no_registrado_no_crea_nada(base):
    conexion, _ = base
    video = _video(conexion)
    with pytest.raises(NoEncontrado):
        service.preparar_analisis(conexion, video, "vision", RegistroAnalizadores())
    assert conexion.execute("SELECT COUNT(*) FROM analisis").fetchone()[0] == 0


def test_preparar_con_video_inexistente(base):
    conexion, _ = base
    with pytest.raises(NoEncontrado):
        service.preparar_analisis(conexion, 999, "audio", registro_con(AnalizadorFalso("audio")))


# -- Persistencia de resultados -------------------------------------------

def test_persistir_resultado_es_idempotente(base):
    conexion, raiz = base
    video = _video(conexion)
    analisis = service.preparar_analisis(conexion, video, "audio", registro_con(AnalizadorFalso("audio")))
    resultado = ResultadoSegmento(senales=(_senal(),), fotogramas=(_miniatura(raiz, video, 500),))

    persistir_en_transaccion(conexion, raiz, analisis.id, resultado)
    persistir_en_transaccion(conexion, raiz, analisis.id, resultado)

    assert _conteo(conexion, "senales", analisis.id) == 1
    assert _conteo(conexion, "fotogramas", analisis.id) == 1


def test_persistir_rechaza_una_ruta_de_fotograma_ajena_sin_escribir_nada(base):
    conexion, raiz = base
    video = _video(conexion)
    analisis = service.preparar_analisis(conexion, video, "audio", registro_con(AnalizadorFalso("audio")))
    resultado = ResultadoSegmento(
        senales=(_senal(),),
        fotogramas=(FotogramaProducido(tiempo_ms=0, ruta_relativa="../clipperai.db"),),
    )
    with pytest.raises(ContratoInvalido):
        persistir_en_transaccion(conexion, raiz, analisis.id, resultado)
    assert _conteo(conexion, "senales", analisis.id) == 0


def test_persistir_exige_que_la_miniatura_exista_en_disco(base):
    conexion, raiz = base
    video = _video(conexion)
    analisis = service.preparar_analisis(conexion, video, "vision", registro_con(AnalizadorFalso("vision")))
    resultado = ResultadoSegmento(
        senales=(_senal("energia_audio"),),
        fotogramas=(FotogramaProducido(tiempo_ms=800, ruta_relativa=f"work/{video}/fotogramas/800.jpg"),),
    )
    with pytest.raises(NoEncontrado):
        persistir_en_transaccion(conexion, raiz, analisis.id, resultado)
    assert _conteo(conexion, "senales", analisis.id) == 0


def test_persistir_con_analisis_inexistente(base):
    conexion, raiz = base
    with pytest.raises(NoEncontrado):
        persistir_en_transaccion(conexion, raiz, 999, ResultadoSegmento())


# -- Consultas ------------------------------------------------------------

@pytest.fixture
def analisis_con_senales(base):
    conexion, raiz = base
    video = _video(conexion)
    analisis = service.preparar_analisis(conexion, video, "audio", registro_con(AnalizadorFalso("audio")))
    persistir_en_transaccion(
        conexion,
        raiz,
        analisis.id,
        ResultadoSegmento(
            senales=(
                _senal("silencio", 0, 1000),
                _senal("cambio_intensidad", 900, 2000),
                _senal("energia_audio", 5000, 6000),
            ),
        ),
    )
    return conexion, raiz, video


def test_listar_senales_devuelve_las_que_se_solapan_ordenadas(analisis_con_senales):
    conexion, _, video = analisis_con_senales
    senales = service.listar_senales(conexion, video, "audio", inicio_ms=950, fin_ms=1100)
    assert [(s.tipo, s.inicio_ms) for s in senales] == [("silencio", 0), ("cambio_intensidad", 900)]


def test_listar_senales_sin_intervalo_respeta_el_limite(analisis_con_senales):
    conexion, _, video = analisis_con_senales
    senales = service.listar_senales(conexion, video, "audio", limite=2)
    assert len(senales) == 2


@pytest.mark.parametrize("inicio, fin, limite", [(1000, 500, 10), (None, None, 0), (None, None, 2001)])
def test_listar_senales_rechaza_intervalo_invertido_o_limite_fuera_de_rango(analisis_con_senales, inicio, fin, limite):
    conexion, _, video = analisis_con_senales
    with pytest.raises(SolicitudInvalida):
        service.listar_senales(conexion, video, "audio", inicio, fin, limite)


def test_listar_senales_de_analisis_inexistente(analisis_con_senales):
    conexion, _, video = analisis_con_senales
    with pytest.raises(NoEncontrado):
        service.listar_senales(conexion, video, "vision")


def test_listar_fotogramas_ordena_por_tiempo(base):
    conexion, raiz = base
    video = _video(conexion)
    analisis = service.preparar_analisis(conexion, video, "audio", registro_con(AnalizadorFalso("audio")))
    persistir_en_transaccion(
        conexion,
        raiz,
        analisis.id,
        ResultadoSegmento(fotogramas=(_miniatura(raiz, video, 2000), _miniatura(raiz, video, 1000))),
    )
    assert [f.tiempo_ms for f in service.listar_fotogramas(conexion, video, "audio")] == [1000, 2000]


def test_ruta_miniatura_devuelve_la_ruta_registrada(base):
    conexion, raiz = base
    video = _video(conexion)
    analisis = service.preparar_analisis(conexion, video, "audio", registro_con(AnalizadorFalso("audio")))
    persistir_en_transaccion(conexion, raiz, analisis.id, ResultadoSegmento(fotogramas=(_miniatura(raiz, video, 40),)))
    ruta = service.ruta_miniatura(conexion, raiz, video, "audio", 40)
    assert ruta.read_bytes() == JPEG_PRUEBA


def test_ruta_miniatura_ignora_una_fila_con_ruta_que_no_es_la_del_almacen(base):
    conexion, raiz = base
    video = _video(conexion)
    analisis = service.preparar_analisis(conexion, video, "audio", registro_con(AnalizadorFalso("audio")))
    # Fila corrupta a propósito: apunta a la base de datos. El servicio no debe servirla.
    conexion.execute(
        "INSERT INTO fotogramas (analisis_id, tiempo_ms, ruta_relativa) VALUES (?, 0, 'clipperai.db')",
        (analisis.id,),
    )
    conexion.commit()
    with pytest.raises(NoEncontrado):
        service.ruta_miniatura(conexion, raiz, video, "audio", 0)


def test_ruta_miniatura_inexistente_no_revela_rutas(base):
    conexion, raiz = base
    video = _video(conexion)
    service.preparar_analisis(conexion, video, "audio", registro_con(AnalizadorFalso("audio")))
    with pytest.raises(NoEncontrado) as error:
        service.ruta_miniatura(conexion, raiz, video, "audio", 7)
    assert str(raiz.raiz) not in str(error.value)


# -- Estado y limpieza ----------------------------------------------------

def test_marcar_estado_rechaza_un_estado_desconocido(base):
    conexion, _ = base
    video = _video(conexion)
    analisis = service.preparar_analisis(conexion, video, "audio", registro_con(AnalizadorFalso("audio")))
    with pytest.raises(ContratoInvalido):
        service.marcar_estado(conexion, analisis.id, "inventado")


def test_marcar_estado_quita_las_rutas_del_error(base, tmp_path):
    conexion, _ = base
    video = _video(conexion)
    analisis = service.preparar_analisis(conexion, video, "audio", registro_con(AnalizadorFalso("audio")))
    service.marcar_estado(conexion, analisis.id, "fallido", error=f"Fallo al leer {tmp_path / 'secreto.mp4'}")
    error = service.obtener_analisis(conexion, video, "audio").error
    assert str(tmp_path) not in error
    assert len(error) <= 500


def test_barrido_no_corre_mientras_hay_un_trabajo_ejecutandose(base):
    conexion, raiz = base
    video = _video(conexion)
    conexion.execute(
        "INSERT INTO trabajos (tipo, estado, claim_token) VALUES ('diagnostico_espera', 'ejecutando', 'token')"
    )
    conexion.commit()
    with pytest.raises(Conflicto):
        service.barrer_fotogramas_huerfanos(conexion, raiz, video)

    conexion.execute("UPDATE trabajos SET estado = 'completado', claim_token = NULL")
    conexion.commit()
    assert service.barrer_fotogramas_huerfanos(conexion, raiz, video) == 0


def test_barrido_elimina_miniaturas_sin_fila(base):
    conexion, raiz = base
    video = _video(conexion)
    analisis = service.preparar_analisis(conexion, video, "audio", registro_con(AnalizadorFalso("audio")))
    persistir_en_transaccion(conexion, raiz, analisis.id, ResultadoSegmento(fotogramas=(_miniatura(raiz, video, 1),)))
    _miniatura(raiz, video, 2)  # Sin fila: queda huérfana.
    assert service.barrer_fotogramas_huerfanos(conexion, raiz, video) == 1
    assert (raiz.raiz / f"work/{video}/fotogramas/1.jpg").exists()
    assert not (raiz.raiz / f"work/{video}/fotogramas/2.jpg").exists()
