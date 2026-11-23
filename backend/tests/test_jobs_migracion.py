import sqlite3

import pytest

from app.db.conexion import conectar
from app.db.migraciones import DIRECTORIO_MIGRACIONES, aplicar_migraciones


def _insertar_trabajo(conexion: sqlite3.Connection, estado: str = "en_cola", claim: str | None = None) -> int:
    cursor = conexion.execute(
        "INSERT INTO trabajos (tipo, estado, claim_token) VALUES ('diagnostico_espera', ?, ?)",
        (estado, claim),
    )
    return cursor.lastrowid


def test_migracion_0003_crea_trabajos_y_segmentos(tmp_path):
    conexion = conectar(tmp_path / "prueba.db")
    try:
        version = aplicar_migraciones(conexion)
        tablas = {fila["name"] for fila in conexion.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert version == 4
        assert {"trabajos", "segmentos_trabajo"} <= tablas
    finally:
        conexion.close()


def test_migracion_0003_conserva_datos_de_una_base_en_version_2(tmp_path):
    ruta = tmp_path / "version2.db"
    conexion = conectar(ruta)
    try:
        for archivo in ("0001_proyectos.sql", "0002_videos.sql"):
            conexion.executescript((DIRECTORIO_MIGRACIONES / archivo).read_text(encoding="utf-8"))
        conexion.execute("PRAGMA user_version = 2")
        conexion.execute("INSERT INTO proyectos (nombre) VALUES ('existente')")
        conexion.commit()

        version = aplicar_migraciones(conexion)

        assert version == 4
        nombres = [fila["nombre"] for fila in conexion.execute("SELECT nombre FROM proyectos")]
        assert nombres == ["existente"]
    finally:
        conexion.close()


def test_unicidad_de_segmento_incluye_tipo_de_analisis(tmp_path):
    conexion = conectar(tmp_path / "prueba.db")
    try:
        aplicar_migraciones(conexion)
        trabajo_id = _insertar_trabajo(conexion)
        conexion.execute(
            "INSERT INTO segmentos_trabajo (trabajo_id, tipo_analisis, indice, inicio_ms, fin_ms, estado) "
            "VALUES (?, 'audio', 0, 0, 1000, 'pendiente')",
            (trabajo_id,),
        )
        # El mismo índice para otro tipo de análisis sí debe admitirse.
        conexion.execute(
            "INSERT INTO segmentos_trabajo (trabajo_id, tipo_analisis, indice, inicio_ms, fin_ms, estado) "
            "VALUES (?, 'video', 0, 0, 1000, 'pendiente')",
            (trabajo_id,),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conexion.execute(
                "INSERT INTO segmentos_trabajo (trabajo_id, tipo_analisis, indice, inicio_ms, fin_ms, estado) "
                "VALUES (?, 'audio', 0, 0, 1000, 'pendiente')",
                (trabajo_id,),
            )
    finally:
        conexion.close()


def test_restricciones_de_estado_y_token(tmp_path):
    conexion = conectar(tmp_path / "prueba.db")
    try:
        aplicar_migraciones(conexion)
        with pytest.raises(sqlite3.IntegrityError):
            _insertar_trabajo(conexion, estado="inventado")
        with pytest.raises(sqlite3.IntegrityError):
            _insertar_trabajo(conexion, estado="en_cola", claim="token-huerfano")
        with pytest.raises(sqlite3.IntegrityError):
            _insertar_trabajo(conexion, estado="ejecutando", claim=None)
    finally:
        conexion.rollback()
        conexion.close()
