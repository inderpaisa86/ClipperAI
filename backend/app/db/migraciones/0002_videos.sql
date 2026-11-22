-- Módulo videos: registros de videos por referencia.
-- El archivo original nunca se modifica ni se copia. La copia gestionada llegará en una fase posterior.
CREATE TABLE videos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    proyecto_id INTEGER NOT NULL REFERENCES proyectos(id) ON DELETE RESTRICT,
    nombre TEXT NOT NULL,
    ruta_original TEXT NOT NULL,
    tamano_bytes INTEGER NOT NULL CHECK (tamano_bytes >= 0),
    duracion_segundos REAL,
    ancho INTEGER NOT NULL CHECK (ancho > 0),
    alto INTEGER NOT NULL CHECK (alto > 0),
    fps REAL,
    codec_video TEXT NOT NULL,
    codec_audio TEXT,
    formato TEXT NOT NULL,
    creado TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE (proyecto_id, ruta_original)
);

CREATE INDEX idx_videos_proyecto ON videos (proyecto_id);
