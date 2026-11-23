-- requiere: claves_externas_desactivadas
-- Módulo analisis: añade el estado 'cancelado' a la tabla analisis.
-- SQLite no permite cambiar un CHECK existente con ALTER TABLE, así que la tabla se reconstruye
-- siguiendo el procedimiento de 12 pasos de SQLite (lang_altertable). Este archivo no abre ni cierra
-- transacciones: lo hace el runner de migraciones, que desactiva las claves externas antes de BEGIN,
-- verifica foreign_key_check e integrity_check antes de COMMIT y restaura foreign_keys al terminar.
-- Las tablas senales y fotogramas referencian analisis por nombre. Al reconstruirla no se borran sus filas
-- porque las claves externas están desactivadas. Al terminar, la referencia vuelve a apuntar a analisis.
-- Las columnas, las restricciones y las acciones ON DELETE CASCADE / SET NULL se conservan.

CREATE TEMP TABLE respaldo_secuencia_analisis AS
    SELECT seq FROM sqlite_sequence WHERE name = 'analisis';

CREATE TABLE analisis_nueva (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id INTEGER NOT NULL REFERENCES videos (id) ON DELETE CASCADE,
    analizador TEXT NOT NULL CHECK (
        length(analizador) BETWEEN 1 AND 32
        AND analizador GLOB '[a-z]*'
        AND analizador NOT GLOB '*[^a-z0-9_]*'
    ),
    version_analizador TEXT NOT NULL CHECK (length(version_analizador) BETWEEN 1 AND 32),
    estado TEXT NOT NULL CHECK (estado IN ('pendiente', 'en_curso', 'completado', 'fallido', 'cancelado')),
    trabajo_id INTEGER REFERENCES trabajos (id) ON DELETE SET NULL,
    error TEXT CHECK (error IS NULL OR length(error) <= 500),
    creado TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    actualizado TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE (video_id, analizador)
);

INSERT INTO analisis_nueva (id, video_id, analizador, version_analizador, estado, trabajo_id, error, creado, actualizado)
    SELECT id, video_id, analizador, version_analizador, estado, trabajo_id, error, creado, actualizado
    FROM analisis;

DROP TABLE analisis;

ALTER TABLE analisis_nueva RENAME TO analisis;

-- Conserva el contador de ids: un id eliminado no vuelve a asignarse.
UPDATE sqlite_sequence
    SET seq = MAX(seq, (SELECT COALESCE(MAX(seq), 0) FROM respaldo_secuencia_analisis))
    WHERE name = 'analisis';

INSERT INTO sqlite_sequence (name, seq)
    SELECT 'analisis', seq FROM respaldo_secuencia_analisis
    WHERE NOT EXISTS (SELECT 1 FROM sqlite_sequence WHERE name = 'analisis');

DROP TABLE respaldo_secuencia_analisis;
