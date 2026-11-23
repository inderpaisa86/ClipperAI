import sqlite3

import pytest

from app.db.conexion import conectar
from app.db.migraciones import DIRECTORIO_MIGRACIONES, aplicar_migraciones


def _migrada(ruta):
    conexion = conectar(ruta)
    aplicar_migraciones(conexion)
    return conexion


def _video(conexion: sqlite3.Connection, nombre: str = "a") -> int:
    proyecto = conexion.execute("INSERT INTO proyectos (nombre) VALUES (?)", (f"p-{nombre}",)).lastrowid
    video = conexion.execute(
        "INSERT INTO videos (proyecto_id, nombre, ruta_original, tamano_bytes, ancho, alto, codec_video, formato) "
        "VALUES (?, ?, ?, 10, 320, 240, 'h264', 'mp4')",
        (proyecto, nombre, f"/medios/{nombre}.mp4"),
    ).lastrowid
    return int(video)


def _analisis(conexion: sqlite3.Connection, video_id: int, analizador: str = "audio", trabajo_id=None) -> int:
    return int(
        conexion.execute(
            "INSERT INTO analisis (video_id, analizador, version_analizador, estado, trabajo_id) "
            "VALUES (?, ?, '1', 'pendiente', ?)",
            (video_id, analizador, trabajo_id),
        ).lastrowid
    )


def _senal(conexion, analisis_id: int, tipo: str = "escena", inicio: int = 0, fin: int = 1000,
           valor: float = 0.5, confianza: float = 0.9) -> None:
    conexion.execute(
        "INSERT INTO senales (analisis_id, tipo, inicio_ms, fin_ms, valor, confianza) VALUES (?, ?, ?, ?, ?, ?)",
        (analisis_id, tipo, inicio, fin, valor, confianza),
    )


def test_migracion_0004_crea_tablas_y_registra_version_4(tmp_path):
    conexion = _migrada(tmp_path / "prueba.db")
    try:
        tablas = {fila["name"] for fila in conexion.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert {"analisis", "senales", "fotogramas"} <= tablas
        assert conexion.execute("PRAGMA user_version").fetchone()[0] == 4
    finally:
        conexion.close()


def test_migracion_0004_conserva_datos_de_una_base_en_version_3(tmp_path):
    ruta = tmp_path / "version3.db"
    conexion = conectar(ruta)
    try:
        for archivo in sorted(DIRECTORIO_MIGRACIONES.glob("*.sql")):
            if archivo.name.startswith(("0001", "0002", "0003")):
                conexion.executescript(archivo.read_text(encoding="utf-8"))
        conexion.execute("PRAGMA user_version = 3")
        conexion.execute("INSERT INTO proyectos (nombre) VALUES ('existente')")
        conexion.commit()
        assert aplicar_migraciones(conexion) == 4
        nombres = [fila["nombre"] for fila in conexion.execute("SELECT nombre FROM proyectos")]
        assert nombres == ["existente"]
        assert conexion.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        conexion.close()


def test_migracion_es_idempotente_y_conserva_analisis(tmp_path):
    conexion = _migrada(tmp_path / "prueba.db")
    try:
        _analisis(conexion, _video(conexion))
        conexion.commit()
        assert aplicar_migraciones(conexion) == 4
        assert conexion.execute("SELECT COUNT(*) FROM analisis").fetchone()[0] == 1
    finally:
        conexion.close()


@pytest.mark.parametrize("analizador", ["Audio", "audio-x", "1audio", "", "a" * 33, "audio sí"])
def test_identificador_de_analizador_invalido_se_rechaza(tmp_path, analizador):
    conexion = _migrada(tmp_path / "prueba.db")
    try:
        video = _video(conexion)
        with pytest.raises(sqlite3.IntegrityError):
            _analisis(conexion, video, analizador=analizador)
    finally:
        conexion.rollback()
        conexion.close()


def test_estado_de_analisis_invalido_se_rechaza(tmp_path):
    conexion = _migrada(tmp_path / "prueba.db")
    try:
        video = _video(conexion)
        with pytest.raises(sqlite3.IntegrityError):
            conexion.execute(
                "INSERT INTO analisis (video_id, analizador, version_analizador, estado) VALUES (?, 'audio', '1', 'raro')",
                (video,),
            )
    finally:
        conexion.rollback()
        conexion.close()


def test_un_analisis_por_video_y_analizador(tmp_path):
    conexion = _migrada(tmp_path / "prueba.db")
    try:
        video = _video(conexion)
        _analisis(conexion, video, "audio")
        _analisis(conexion, video, "vision")
        with pytest.raises(sqlite3.IntegrityError):
            _analisis(conexion, video, "audio")
    finally:
        conexion.rollback()
        conexion.close()


@pytest.mark.parametrize(
    "tipo, inicio, fin, valor, confianza",
    [
        ("Escena", 0, 10, 0.5, 0.5),
        ("escena", -1, 10, 0.5, 0.5),
        ("escena", 10, 5, 0.5, 0.5),
        ("escena", 0, 10, 1.5, 0.5),
        ("escena", 0, 10, 0.5, -0.1),
    ],
)
def test_senal_con_datos_invalidos_se_rechaza(tmp_path, tipo, inicio, fin, valor, confianza):
    conexion = _migrada(tmp_path / "prueba.db")
    try:
        analisis = _analisis(conexion, _video(conexion))
        with pytest.raises(sqlite3.IntegrityError):
            _senal(conexion, analisis, tipo, inicio, fin, valor, confianza)
    finally:
        conexion.rollback()
        conexion.close()


def test_senal_repetida_se_ignora_sin_duplicar(tmp_path):
    conexion = _migrada(tmp_path / "prueba.db")
    try:
        analisis = _analisis(conexion, _video(conexion))
        for _ in range(2):
            conexion.execute(
                "INSERT OR IGNORE INTO senales (analisis_id, tipo, inicio_ms, fin_ms, valor, confianza) "
                "VALUES (?, 'escena', 0, 1000, 0.7, 0.8)",
                (analisis,),
            )
        assert conexion.execute("SELECT COUNT(*) FROM senales").fetchone()[0] == 1
    finally:
        conexion.close()


def test_fotograma_unico_por_tiempo_dentro_de_un_analisis(tmp_path):
    conexion = _migrada(tmp_path / "prueba.db")
    try:
        analisis = _analisis(conexion, _video(conexion), "vision")
        conexion.execute(
            "INSERT INTO fotogramas (analisis_id, tiempo_ms, ruta_relativa) VALUES (?, 1000, 'work/1/fotogramas/1000.jpg')",
            (analisis,),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conexion.execute(
                "INSERT INTO fotogramas (analisis_id, tiempo_ms, ruta_relativa) VALUES (?, 1000, 'work/1/fotogramas/1000b.jpg')",
                (analisis,),
            )
    finally:
        conexion.rollback()
        conexion.close()


def test_eliminar_video_borra_sus_analisis_y_resultados_y_no_los_de_otro(tmp_path):
    conexion = _migrada(tmp_path / "prueba.db")
    try:
        video_a = _video(conexion, "a")
        video_b = _video(conexion, "b")
        analisis_a = _analisis(conexion, video_a)
        analisis_b = _analisis(conexion, video_b)
        _senal(conexion, analisis_a)
        _senal(conexion, analisis_b)
        conexion.execute("DELETE FROM videos WHERE id = ?", (video_a,))
        conexion.commit()
        assert conexion.execute("SELECT COUNT(*) FROM analisis WHERE video_id = ?", (video_a,)).fetchone()[0] == 0
        assert conexion.execute("SELECT COUNT(*) FROM senales WHERE analisis_id = ?", (analisis_a,)).fetchone()[0] == 0
        assert conexion.execute("SELECT COUNT(*) FROM senales WHERE analisis_id = ?", (analisis_b,)).fetchone()[0] == 1
    finally:
        conexion.close()


def test_eliminar_trabajo_deja_el_analisis_sin_referencia(tmp_path):
    conexion = _migrada(tmp_path / "prueba.db")
    try:
        trabajo = int(conexion.execute(
            "INSERT INTO trabajos (tipo, estado) VALUES ('diagnostico_espera', 'en_cola')"
        ).lastrowid)
        analisis = _analisis(conexion, _video(conexion), trabajo_id=trabajo)
        conexion.execute("DELETE FROM trabajos WHERE id = ?", (trabajo,))
        conexion.commit()
        fila = conexion.execute("SELECT trabajo_id FROM analisis WHERE id = ?", (analisis,)).fetchone()
        assert fila["trabajo_id"] is None
    finally:
        conexion.close()
