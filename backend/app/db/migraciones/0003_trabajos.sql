-- Módulo jobs: cola de trabajos en segundo plano y sus segmentos.
-- claim_token identifica la ejecución vigente. Solo el proceso que posee ese token puede confirmar resultados.
-- pid e identidad_proceso (hora de creación del sistema) permiten terminar un proceso recuperado sin matar otro.
CREATE TABLE trabajos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo TEXT NOT NULL CHECK (length(tipo) BETWEEN 1 AND 64),
    estado TEXT NOT NULL CHECK (estado IN ('en_cola', 'ejecutando', 'completado', 'fallido', 'cancelado')),
    progreso INTEGER NOT NULL DEFAULT 0 CHECK (progreso BETWEEN 0 AND 100),
    payload_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(payload_json)),
    cancelacion_solicitada INTEGER NOT NULL DEFAULT 0 CHECK (cancelacion_solicitada IN (0, 1)),
    intentos INTEGER NOT NULL DEFAULT 0 CHECK (intentos >= 0),
    claim_token TEXT,
    pid INTEGER,
    identidad_proceso TEXT,
    latido TEXT,
    error TEXT CHECK (error IS NULL OR length(error) <= 2000),
    creado TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    actualizado TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    CHECK ((estado = 'ejecutando') = (claim_token IS NOT NULL)),
    CHECK (estado = 'ejecutando' OR (pid IS NULL AND identidad_proceso IS NULL))
);

CREATE INDEX idx_trabajos_estado ON trabajos (estado, id);

CREATE TABLE segmentos_trabajo (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trabajo_id INTEGER NOT NULL REFERENCES trabajos (id) ON DELETE CASCADE,
    tipo_analisis TEXT NOT NULL CHECK (length(tipo_analisis) BETWEEN 1 AND 64),
    indice INTEGER NOT NULL CHECK (indice >= 0),
    inicio_ms INTEGER NOT NULL CHECK (inicio_ms >= 0),
    fin_ms INTEGER NOT NULL CHECK (fin_ms > inicio_ms),
    estado TEXT NOT NULL CHECK (estado IN ('pendiente', 'procesando', 'completado', 'fallido')),
    salida_ruta TEXT,
    salida_tamano INTEGER CHECK (salida_tamano IS NULL OR salida_tamano >= 0),
    version_analizador TEXT,
    actualizado TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE (trabajo_id, tipo_analisis, indice)
);

CREATE INDEX idx_segmentos_trabajo_estado ON segmentos_trabajo (trabajo_id, estado);
