-- Módulo analisis: análisis por video, señales normalizadas y fotogramas representativos.
-- Dueño exclusivo de estas tablas. Los tiempos son enteros en milisegundos.
-- Los fotogramas son archivos en data/work. Aquí solo se guarda su ruta relativa a data/.
CREATE TABLE analisis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id INTEGER NOT NULL REFERENCES videos (id) ON DELETE CASCADE,
    analizador TEXT NOT NULL CHECK (
        length(analizador) BETWEEN 1 AND 32
        AND analizador GLOB '[a-z]*'
        AND analizador NOT GLOB '*[^a-z0-9_]*'
    ),
    version_analizador TEXT NOT NULL CHECK (length(version_analizador) BETWEEN 1 AND 32),
    estado TEXT NOT NULL CHECK (estado IN ('pendiente', 'en_curso', 'completado', 'fallido')),
    trabajo_id INTEGER REFERENCES trabajos (id) ON DELETE SET NULL,
    error TEXT CHECK (error IS NULL OR length(error) <= 500),
    creado TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    actualizado TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE (video_id, analizador)
);
CREATE TABLE senales (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    analisis_id INTEGER NOT NULL REFERENCES analisis (id) ON DELETE CASCADE,
    tipo TEXT NOT NULL CHECK (
        length(tipo) BETWEEN 1 AND 32
        AND tipo GLOB '[a-z]*'
        AND tipo NOT GLOB '*[^a-z0-9_]*'
    ),
    inicio_ms INTEGER NOT NULL CHECK (inicio_ms >= 0),
    fin_ms INTEGER NOT NULL CHECK (fin_ms >= inicio_ms),
    valor REAL NOT NULL CHECK (valor >= 0 AND valor <= 1),
    confianza REAL NOT NULL CHECK (confianza >= 0 AND confianza <= 1),
    -- Reprocesar un segmento produce las mismas filas, que se ignoran en lugar de duplicarse.
    UNIQUE (analisis_id, tipo, inicio_ms, fin_ms)
);
CREATE INDEX idx_senales_tiempo ON senales (analisis_id, inicio_ms, fin_ms);
CREATE TABLE fotogramas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    analisis_id INTEGER NOT NULL REFERENCES analisis (id) ON DELETE CASCADE,
    tiempo_ms INTEGER NOT NULL CHECK (tiempo_ms >= 0),
    ruta_relativa TEXT NOT NULL CHECK (length(ruta_relativa) BETWEEN 1 AND 255),
    creado TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE (analisis_id, tiempo_ms)
);
