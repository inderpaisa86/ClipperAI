from app.db.conexion import conectar
from app.db.migraciones import aplicar_migraciones


def test_migraciones_crean_tablas_y_registran_version(tmp_path):
    conexion = conectar(tmp_path / "prueba.db")
    try:
        version = aplicar_migraciones(conexion)

        tablas = {
            fila["name"]
            for fila in conexion.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        assert version == 5
        assert {"proyectos", "videos"} <= tablas
        assert conexion.execute("PRAGMA user_version").fetchone()[0] == 5
    finally:
        conexion.close()


def test_migraciones_son_idempotentes(tmp_path):
    conexion = conectar(tmp_path / "prueba.db")
    try:
        aplicar_migraciones(conexion)
        conexion.execute("INSERT INTO proyectos (nombre) VALUES ('conservado')")
        conexion.commit()

        version = aplicar_migraciones(conexion)

        assert version == 5
        assert conexion.execute("SELECT COUNT(*) FROM proyectos").fetchone()[0] == 1
    finally:
        conexion.close()


def test_claves_externas_estan_activas(tmp_path):
    conexion = conectar(tmp_path / "prueba.db")
    try:
        aplicar_migraciones(conexion)

        assert conexion.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert conexion.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    finally:
        conexion.close()
