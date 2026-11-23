"""Migración 0005: reconstrucción de `analisis` con el estado `cancelado`.

Las pruebas usan bases temporales con datos. Nunca se ejecutan contra la base real.
"""

import shutil
import sqlite3
from pathlib import Path

import pytest

from app.db.conexion import conectar
from app.db.migraciones import DIRECTORIO_MIGRACIONES, aplicar_migraciones


def _base_en_version_4(ruta: Path) -> sqlite3.Connection:
    conexion = conectar(ruta)
    aplicar_migraciones(conexion, hasta=4)
    return conexion


def _poblar(conexion: sqlite3.Connection) -> None:
    """Datos que deben sobrevivir a la migración: videos, trabajos, análisis, señales y fotogramas."""
    conexion.execute("INSERT INTO proyectos (nombre) VALUES ('Proyecto')")
    conexion.execute(
        "INSERT INTO videos (proyecto_id, nombre, ruta_original, tamano_bytes, ancho, alto, codec_video, formato) "
        "VALUES (1, 'v.mp4', '/medios/v.mp4', 10, 1280, 720, 'h264', 'mp4')"
    )
    conexion.execute(
        "INSERT INTO videos (proyecto_id, nombre, ruta_original, tamano_bytes, ancho, alto, codec_video, formato) "
        "VALUES (1, 'w.mp4', '/medios/w.mp4', 10, 1280, 720, 'h264', 'mp4')"
    )
    conexion.execute(
        "INSERT INTO trabajos (tipo, estado, payload_json, creado, actualizado) "
        "VALUES ('diagnostico_espera', 'completado', '{}', 't', 't')"
    )
    conexion.execute(
        "INSERT INTO analisis (video_id, analizador, version_analizador, estado, trabajo_id, creado, actualizado) "
        "VALUES (1, 'audio', '1.0.0', 'completado', 1, 't1', 't2')"
    )
    conexion.execute(
        "INSERT INTO analisis (video_id, analizador, version_analizador, estado, error, creado, actualizado) "
        "VALUES (2, 'audio', '1.0.0', 'fallido', 'Fallo previo.', 't3', 't4')"
    )
    # Un análisis eliminado deja su id libre en la tabla, pero el contador debe seguir avanzando.
    conexion.execute(
        "INSERT INTO analisis (video_id, analizador, version_analizador, estado, creado, actualizado) "
        "VALUES (2, 'vision', '1', 'fallido', 't', 't')"
    )
    conexion.execute("DELETE FROM analisis WHERE id = 3")
    conexion.execute(
        "INSERT INTO senales (analisis_id, tipo, inicio_ms, fin_ms, valor, confianza) "
        "VALUES (1, 'silencio', 0, 500, 0.5, 0.9), (1, 'energia_audio', 500, 700, 0.2, 1.0)"
    )
    conexion.execute(
        "INSERT INTO fotogramas (analisis_id, tiempo_ms, ruta_relativa, creado) "
        "VALUES (1, 1000, 'work/1/fotogramas/1000.jpg', 't')"
    )
    conexion.commit()


def _foto(conexion: sqlite3.Connection) -> dict:
    return {
        "analisis": [tuple(fila) for fila in conexion.execute(
            "SELECT id, video_id, analizador, version_analizador, estado, trabajo_id, error, creado, actualizado "
            "FROM analisis ORDER BY id"
        )],
        "senales": conexion.execute("SELECT COUNT(*) FROM senales").fetchone()[0],
        "fotogramas": conexion.execute("SELECT COUNT(*) FROM fotogramas").fetchone()[0],
    }


def test_migracion_conserva_registros_indices_y_referencias(tmp_path):
    conexion = _base_en_version_4(tmp_path / "v4.db")
    _poblar(conexion)
    antes = _foto(conexion)
    version = aplicar_migraciones(conexion)

    assert version == 5
    assert conexion.execute("PRAGMA user_version").fetchone()[0] == 5
    assert _foto(conexion)["analisis"] == antes["analisis"]
    assert _foto(conexion)["senales"] == antes["senales"] == 2
    assert _foto(conexion)["fotogramas"] == antes["fotogramas"] == 1
    assert conexion.execute("PRAGMA foreign_key_check").fetchall() == []
    assert conexion.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert conexion.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_restricciones_nuevas_y_antiguas_siguen_vigentes(tmp_path):
    conexion = _base_en_version_4(tmp_path / "v4.db")
    _poblar(conexion)
    aplicar_migraciones(conexion)

    with pytest.raises(sqlite3.IntegrityError):
        conexion.execute(
            "INSERT INTO analisis (video_id, analizador, version_analizador, estado, creado, actualizado) "
            "VALUES (1, 'vision', '1', 'raro', 't', 't')"
        )
    conexion.rollback()
    with pytest.raises(sqlite3.IntegrityError):
        conexion.execute(
            "INSERT INTO analisis (video_id, analizador, version_analizador, estado, creado, actualizado) "
            "VALUES (1, 'audio', '1', 'completado', 't', 't')"
        )
    conexion.rollback()
    conexion.execute(
        "INSERT INTO analisis (video_id, analizador, version_analizador, estado, creado, actualizado) "
        "VALUES (1, 'vision', '1', 'cancelado', 't', 't')"
    )
    conexion.commit()
    assert conexion.execute("SELECT estado FROM analisis WHERE video_id = 1 AND analizador = 'vision'").fetchone()[0] == "cancelado"


def test_contador_de_ids_no_reutiliza_ids_eliminados(tmp_path):
    conexion = _base_en_version_4(tmp_path / "v4.db")
    _poblar(conexion)
    maximo_antes = conexion.execute("SELECT MAX(id) FROM analisis").fetchone()[0]
    eliminado = conexion.execute("SELECT seq FROM sqlite_sequence WHERE name = 'analisis'").fetchone()[0]
    aplicar_migraciones(conexion)
    conexion.execute(
        "INSERT INTO analisis (video_id, analizador, version_analizador, estado, creado, actualizado) "
        "VALUES (2, 'vision', '1', 'cancelado', 't', 't')"
    )
    nuevo = conexion.execute("SELECT MAX(id) FROM analisis").fetchone()[0]
    assert nuevo > maximo_antes
    assert nuevo == eliminado + 1


def test_relaciones_on_delete_siguen_funcionando_tras_la_migracion(tmp_path):
    conexion = _base_en_version_4(tmp_path / "v4.db")
    _poblar(conexion)
    aplicar_migraciones(conexion)

    conexion.execute("DELETE FROM trabajos WHERE id = 1")
    conexion.commit()
    assert conexion.execute("SELECT trabajo_id FROM analisis WHERE id = 1").fetchone()[0] is None

    conexion.execute("DELETE FROM videos WHERE id = 1")
    conexion.commit()
    assert conexion.execute("SELECT COUNT(*) FROM analisis WHERE video_id = 1").fetchone()[0] == 0
    assert conexion.execute("SELECT COUNT(*) FROM senales").fetchone()[0] == 0
    assert conexion.execute("SELECT COUNT(*) FROM fotogramas").fetchone()[0] == 0
    assert conexion.execute("PRAGMA foreign_key_check").fetchall() == []


def test_migracion_es_idempotente(tmp_path):
    conexion = _base_en_version_4(tmp_path / "v4.db")
    _poblar(conexion)
    aplicar_migraciones(conexion)
    antes = _foto(conexion)
    assert aplicar_migraciones(conexion) == 5
    assert _foto(conexion) == antes


def _migraciones_con_0005_rota(destino: Path, sql_extra: str) -> Path:
    """Copia las migraciones y añade a la 0005 una sentencia extra que debe hacer fallar la migración."""
    carpeta = destino / "migraciones"
    shutil.copytree(DIRECTORIO_MIGRACIONES, carpeta)
    ruta = carpeta / "0005_analisis_cancelado.sql"
    ruta.write_text(ruta.read_text(encoding="utf-8") + "\n" + sql_extra + "\n", encoding="utf-8")
    return carpeta


@pytest.mark.parametrize(
    "sql_extra",
    [
        # Referencia rota: una señal que apunta a un análisis que no existe. Lo detecta foreign_key_check.
        "INSERT INTO senales (analisis_id, tipo, inicio_ms, fin_ms, valor, confianza) "
        "VALUES (999999, 'silencio', 0, 500, 0.5, 0.9);",
        # Error de sintaxis: lo detecta la propia ejecución de la sentencia.
        "CREATE TABLE romper (;",
    ],
)
def test_fallo_de_migracion_no_deja_la_base_a_medias(tmp_path, sql_extra):
    ruta = tmp_path / "v4.db"
    conexion = _base_en_version_4(ruta)
    _poblar(conexion)
    antes = _foto(conexion)
    conexion.close()

    carpeta = _migraciones_con_0005_rota(tmp_path, sql_extra)
    conexion = conectar(ruta)
    try:
        with pytest.raises(sqlite3.Error):
            aplicar_migraciones(conexion, directorio=carpeta)
        assert conexion.in_transaction is False
        assert conexion.execute("PRAGMA user_version").fetchone()[0] == 4
        # Claves externas restauradas aunque la migración fallara.
        assert conexion.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        # La tabla conserva el esquema antiguo: `cancelado` aún no es válido.
        with pytest.raises(sqlite3.IntegrityError):
            conexion.execute(
                "INSERT INTO analisis (video_id, analizador, version_analizador, estado, creado, actualizado) "
                "VALUES (1, 'vision', '1', 'cancelado', 't', 't')"
            )
        conexion.rollback()
        assert _foto(conexion) == antes
        assert conexion.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conexion.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        conexion.close()


def test_la_migracion_restaura_claves_externas_desactivadas_previamente(tmp_path):
    """Si la base llega con `foreign_keys` desactivado, la migración lo deja como estaba."""
    conexion = _base_en_version_4(tmp_path / "v4.db")
    _poblar(conexion)
    conexion.execute("PRAGMA foreign_keys = OFF")
    aplicar_migraciones(conexion)
    assert conexion.execute("PRAGMA foreign_keys").fetchone()[0] == 0
    conexion.execute("PRAGMA foreign_keys = ON")
    conexion.close()
