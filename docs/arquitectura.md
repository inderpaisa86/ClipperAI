# ClipperAI: Arquitectura técnica

**Versión:** 1.5
**Estado:** Fase 1 en curso. Backend, frontend, proxy y Módulo 1 (videos) implementados. Pendiente de aprobación el siguiente módulo.
**Tipo:** Aplicación local de edición inteligente de video.

Las decisiones con su fecha y contexto están en `docs/decisiones.md`. Este documento describe cómo se aplican.

## 1. Visión

ClipperAI analiza contenido audiovisual y propone clips listos para edición y publicación.

- Es universal. No depende de un juego ni de una plataforma.
- Los perfiles de análisis son configuración sobre un motor común. Se pueden añadir perfiles sin cambiar código.
- Todo el procesamiento y almacenamiento ocurre en el equipo del usuario. Ningún video sale del equipo.

## 2. Stack aprobado

| Área | Tecnología |
|---|---|
| Frontend | Next.js (App Router), Node.js 24.19.0, npm 11.17.0 |
| Backend | Python 3.12, FastAPI, gestionado con uv y archivo de bloqueo |
| Multimedia | FFmpeg y FFprobe 9.1 |
| Visión | OpenCV (heurísticas en el MVP) |
| Transcripción | faster-whisper, modelo `small`, CPU, INT8. Configurable a `base` |
| Base de datos | SQLite en modo WAL |
| Cola de trabajos | Tabla SQLite con worker propio. Sin Celery ni Redis |
| Deep Learning | PyTorch, en una fase posterior, detrás de una interfaz |
| Control de versiones | Git 2.55.0 |

## 3. Plataformas

**Desarrollo actual:** Windows 11 Pro de 64 bits, Intel Core i7-1165G7 (4 núcleos, 8 hilos), 15,6 GB de RAM utilizable, Intel Iris Xe.

**Plataformas objetivo:** Windows 10/11 x64, macOS Intel (x86_64) y macOS Apple Silicon (arm64).

Solo Windows se instala y se prueba en esta etapa. Las decisiones de arquitectura no deben bloquear macOS (D-017).

| Requisito | Windows 10/11 | macOS Intel | macOS Apple Silicon |
|---|---|---|---|
| Python 3.12 | Instalador de winget o python.org. También `uv python install 3.12` | Igual, con `uv python install 3.12` o Homebrew | Igual |
| Node.js 24 y npm | winget o instalador oficial | Homebrew o instalador oficial | Igual, con binarios arm64 |
| FFmpeg y FFprobe 9.1 | `winget install Gyan.FFmpeg` | `brew install ffmpeg` | `brew install ffmpeg` (build arm64) |
| Aceleración de video | Intel Quick Sync (`h264_qsv`), si el driver lo expone | VideoToolbox (`h264_videotoolbox`) | VideoToolbox |
| Script de arranque | `scripts/arrancar_windows.ps1` | `scripts/arrancar_macos.sh` | `scripts/arrancar_macos.sh` |
| Permisos del token | Perfil de usuario | `chmod 600` | `chmod 600` |
| Aceleración de IA (fase posterior) | CPU | CPU | Por evaluar: PyTorch MPS. faster-whisper usa CPU |

Notas:

- El nombre de instalación de FFmpeg depende de la plataforma. El backend muestra la instrucción correcta si no lo encuentra.
- macOS usa un sistema de archivos sin distinción de mayúsculas por defecto. No se deben depender de nombres de archivo que solo difieran en mayúsculas.

## 4. Principios de diseño

1. **Módulos por dominio.** Cada módulo de `backend/app/modules/` es dueño de sus datos. Un módulo nunca lee ni escribe las tablas de otro. Para obtener datos de otro módulo, llama a su servicio.
2. **Analizadores como plugins.** Un analizador produce señales normalizadas y no conoce al motor de puntuación. Agregar un analizador o un modelo no modifica `scoring`, `candidates` ni `api`.
3. **Perfiles como datos.** Un perfil es un archivo JSON validado. Sus pesos y umbrales son datos. No contiene lógica específica de un juego.
4. **Archivos solo cuando se necesitan.** No se crean archivos vacíos por obligación. Cada módulo tiene `router.py`, `service.py`, `repository.py` y `schemas.py` solo si la lógica los requiere.
5. **Procesamiento seguro ante fallos.** Todo estado de trabajo se persiste antes de reanudarse.
6. **Independencia de plataforma.** El código del núcleo no contiene rutas, nombres de herramientas ni llamadas específicas de un sistema operativo. Esas diferencias viven en `core/plataforma.py` y `core/herramientas.py`.

## 5. Estructura objetivo

```
ClipperAI/
├─ README.md
├─ AGENTS.md
├─ .gitignore
├─ .gitattributes                 # Finales de línea LF para scripts
├─ docs/
│  ├─ arquitectura.md
│  ├─ decisiones.md
│  └─ api.md                      # Se genera a partir de OpenAPI
├─ backend/
│  ├─ pyproject.toml              # Dependencias (uv)
│  ├─ uv.lock                     # Bloqueo reproducible, válido para todas las plataformas
│  ├─ .python-version             # 3.12
│  ├─ app/
│  │  ├─ main.py                  # Aplicación FastAPI, ciclo de vida y middleware
│  │  ├─ core/
│  │  │  ├─ configuracion.py      # Settings desde variables de entorno
│  │  │  ├─ plataforma.py         # Detección de sistema y arquitectura
│  │  │  ├─ herramientas.py       # Resolución de FFmpeg y FFprobe
│  │  │  ├─ rutas.py              # Acceso seguro al directorio de datos
│  │  │  └─ seguridad.py          # Token, Origin, Host
│  │  ├─ db/
│  │  │  └─ conexion.py           # Conexión SQLite en modo WAL
│  │  ├─ jobs/                    # Cola persistente, worker, recuperación (Fase 2)
│  │  ├─ plugins/                 # Contrato Analyzer y tipo Señal (Fase 2)
│  │  ├─ ml/                      # Interfaces de modelos (Fase 3)
│  │  ├─ perfiles/                # Perfiles JSON: automatico.json, gaming.json (Fase 3)
│  │  └─ modules/
│  │     ├─ sistema/             # Salud del servicio y diagnóstico
│  │     ├─ videos/               # Importación, metadatos, streaming (Fase 1)
│  │     ├─ projects/             # Proyectos (Fase 1)
│  │     ├─ audio/                # Extracción de audio, energía, silencios (Fase 2)
│  │     ├─ vision/               # Escenas, movimiento, brillo, fotogramas (Fase 2)
│  │     ├─ transcription/        # faster-whisper por segmentos (Fase 3)
│  │     ├─ scoring/              # Fusión de señales según perfil (Fase 3)
│  │     ├─ candidates/           # Duración, inicio y fin, deduplicación (Fase 3)
│  │     ├─ clips/                # Estado: pendiente, aprobado, descartado (Fase 4)
│  │     ├─ editing/              # Ajuste de cortes y subtítulos SRT (Fase 4)
│  │     ├─ export/               # Render con FFmpeg (Fase 4)
│  │     └─ preferences/          # Registro de decisiones del usuario (Fase 5)
│  └─ tests/
├─ frontend/                      # Next.js 16, App Router, TypeScript
│  ├─ package.json
│  ├─ package-lock.json
│  ├─ next.config.ts
│  ├─ tsconfig.json
│  ├─ eslint.config.mjs
│  └─ src/
│     ├─ app/
│     │  ├─ layout.tsx            # Raíz de la aplicación, idioma y metadatos
│     │  ├─ page.tsx             # Página principal
│     │  ├─ globals.css
│     │  └─ api/backend/[...ruta]/route.ts   # Proxy al backend (solo GET permitido)
│     ├─ components/              # Cabecera, estado del backend, y futuros componentes
│     └─ lib/
│        ├─ api/                  # Cliente REST del navegador (solo habla con el proxy)
│        ├─ proxy/                # Lista blanca de destinos, validación y reenvío
│        └─ servidor/             # Configuración y lectura del token (solo servidor)
├─ scripts/
│  ├─ arrancar_windows.ps1
│  └─ arrancar_macos.sh
└─ data/                          # Fuera de Git
```

Los directorios de las fases futuras no se crean hasta que la fase empiece.

## 6. Importación de videos

**Modo por defecto: referencia.** La base de datos guarda la ruta original del archivo. El video no se duplica.

**Modo opcional: copia.** El usuario elige copiar el video a `data/media/<video_id>/`. ClipperAI gestiona esa copia de forma independiente.

**Cómo se selecciona el archivo.** El navegador no entrega rutas absolutas. Para el MVP hay dos caminos, ambos validados por el backend:

- El usuario escribe o pega la ruta en la interfaz.
- Un selector de archivos nativo del sistema, abierto por el backend. En Windows es un diálogo del sistema. En macOS se usa el selector nativo equivalente. El backend devuelve la ruta elegida y el frontend la envía al endpoint de importación.

Validaciones obligatorias en el backend:

- La ruta existe, es un archivo regular y no es un enlace simbólico. Las referencias pueden apuntar a cualquier ubicación elegida por el usuario (D-024).
- La extensión está en la lista de formatos admitidos.
- FFprobe puede leer el archivo. Si no puede, la importación se rechaza con un mensaje claro.
- No se aceptan subidas por `multipart` de archivos de video.

## 7. Comunicación y seguridad

El backend escucha solo en `127.0.0.1:8000`. CORS no basta como protección, así que se aplican cuatro controles:

1. **Validación de `Origin`.** Si la petición trae cabecera `Origin`, debe ser `http://localhost:3000` o `http://127.0.0.1:3000`. Cualquier otro origen recibe 403.
2. **Validación de `Host`.** Solo se aceptan `127.0.0.1:8000` y `localhost:8000`. Esto impide ataques de DNS rebinding.
3. **Token de sesión.** El backend genera un token aleatorio de 256 bits (`secrets.token_urlsafe(32)`) en cada arranque, según D-018. Lo escribe en `data/runtime/sesion.token`. Todos los endpoints `/api/v1` exigen la cabecera `X-ClipperAI-Token`, comparada con `hmac.compare_digest`.
4. **Proxy en Next.js.** El navegador no recibe el token. Un route handler del servidor de Next.js (`app/api/backend/[...ruta]/route.ts`) lee el token del archivo y reenvía la petición al backend. Las peticiones sin cabecera `Origin` (las del servidor de Next.js) solo se aceptan con token válido.

Los endpoints de video reenvían las cabeceras `Range` y el cuerpo como flujo, para que el reproductor pueda buscar posiciones.

### 7.1 Proxy del frontend

El proxy es el único camino entre el navegador y el backend. Cada petición pasa por estas comprobaciones en orden:

1. **Host.** Debe ser `localhost:3000` o `127.0.0.1:3000`. Así, un equipo de la red local que alcance el servidor de Next.js no puede usar el proxy.
2. **Origin.** Si existe, debe ser `http://localhost:3000` o `http://127.0.0.1:3000`.
3. **Sec-Fetch-Site.** Si vale `cross-site`, se rechaza.
4. **Lista blanca de destinos.** Solo se reenvían las rutas registradas en `lib/proxy/destinos.ts`. Cada segmento debe tener letras, números, guion o guion bajo. Cualquier otra ruta recibe 400 o 404. Hoy la única ruta permitida es `GET /api/backend/salud`.
5. **Token.** Se lee del archivo `data/runtime/sesion.token` en cada petición. Si falta o no tiene forma válida, responde 503.
6. **Reenvío.** Se llama al backend por `127.0.0.1:8000` sin cabecera `Origin`, así que el backend la acepta con el token. Solo se copian cabeceras de una lista blanca, en ambos sentidos.

Reglas de configuración del servidor de Next.js:

- `CLIPPERAI_BACKEND_URL` solo admite `http://localhost` o `http://127.0.0.1`. Su valor por defecto es `http://127.0.0.1:8000`.
- `CLIPPERAI_DATA_DIR` indica la raíz de datos. Por defecto es `<repositorio>/data`.
- Ninguna de estas variables usa el prefijo `NEXT_PUBLIC_`. El módulo que lee el token importa `node:fs`, así que el build falla si un componente de cliente lo intenta importar.
- El servidor de desarrollo y el de producción se enlazan a `127.0.0.1`, nunca a todas las interfaces.
- Las respuestas del proxy llevan `Cache-Control: no-store`. Los errores nunca incluyen el token ni rutas del sistema.

**Otras reglas:**

- Los subprocesos de FFmpeg y FFprobe se lanzan con argumentos en lista, nunca con cadenas de shell.
- El texto de subtítulos se escapa antes de escribirse en archivos SRT.
- La ruta de FFmpeg se resuelve según la sección 8.2: configuración, luego PATH.

**Tareas largas.** Los endpoints que procesan crean un trabajo y devuelven `job_id`. El frontend consulta `GET /api/v1/jobs/{id}` cada 2 segundos.

## 8. Configuración y herramientas

### 8.1 Variables de entorno

Todas usan el prefijo `CLIPPERAI_`.

| Variable | Propósito | Por defecto |
|---|---|---|
| `CLIPPERAI_DATA_DIR` | Directorio de datos | `<repositorio>/data` |
| `CLIPPERAI_FFMPEG` | Ruta explícita a `ffmpeg` | Búsqueda en PATH |
| `CLIPPERAI_FFPROBE` | Ruta explícita a `ffprobe` | Búsqueda en PATH |

La dirección del servidor (`127.0.0.1:8000`) no es configurable. Así se evita exponer la API por error.

### 8.2 Resolución de herramientas

`core/herramientas.py` busca `ffmpeg` y `ffprobe`:

1. Si la variable de entorno tiene un valor, usa esa ruta. Si no existe, falla con un error claro. No hace búsqueda alternativa.
2. Si no hay variable, usa `shutil.which`.
3. Si nada funciona, devuelve un error con la instrucción de instalación de la plataforma actual.

Después de encontrar el ejecutable, ejecuta `-version` para confirmar que funciona.

## 9. Cola de trabajos y recuperación

### 9.1 Ejecución

- Los trabajos se guardan en la tabla `trabajos`. Estados: `en_cola`, `ejecutando`, `completado`, `fallido`, `cancelado`.
- El worker ejecuta un trabajo pesado a la vez.
- Los trabajos pesados corren en un proceso aparte. Al terminar, libera su memoria y la API sigue respondiendo.
- El worker actualiza `latido` al menos cada 10 segundos y al terminar cada segmento.
- **Cancelación:** la API marca `cancelacion_solicitada = true`. El worker lo revisa entre segmentos y termina de forma ordenada.

### 9.2 Trabajo por segmentos

El análisis se divide en segmentos de duración fija. Cada segmento tiene una fila en `segmentos_trabajo`:

- `trabajo_id`, `tipo_analisis`, `indice`, `inicio`, `fin`
- `estado`: `pendiente`, `procesando`, `completado`, `fallido`
- `salida_ruta` y `salida_tamano`
- `version_analizador`: si cambia la versión del analizador, sus resultados previos se invalidan.

**Escritura atómica.** Cada salida se escribe en un archivo temporal (`*.tmp`) y luego se renombra con `os.replace`. Solo después del renombrado se marca el segmento como `completado`.

### 9.3 Recuperación tras un cierre inesperado

Al arrancar el backend:

1. Los trabajos en `ejecutando` cuyo `latido` tiene más de 60 segundos de antigüedad pasan a `en_cola`.
2. Los segmentos en `procesando` vuelven a `pendiente`.
3. Un segmento `completado` se omite solo si su archivo de salida existe, su tamaño coincide con `salida_tamano` y su versión de analizador sigue vigente.
4. Los archivos `*.tmp` huérfanos se eliminan.

Así, ante un apagón de Windows, se reprocesan únicamente los segmentos que no terminaron de forma verificable.

## 10. Perfiles de análisis

- Un perfil es un archivo JSON en `backend/app/perfiles/`, validado con Pydantic al arrancar.
- Campos principales: `id`, `nombre`, `descripcion`, `duracion_clip` (mínima, máxima y objetivo en segundos), `pesos` (por tipo de señal) y `umbral_minimo`.
- Agregar un perfil consiste en agregar un archivo JSON. No se modifica código.
- Los perfiles creados por el usuario se guardarán en `data/perfiles/` en una fase posterior.

**MVP: dos perfiles.**

- **`automatico`:** pesos generales sobre escenas, movimiento, energía de audio y transcripción.
- **`gaming`:** primer escenario de pruebas con Warzone. Ajusta pesos hacia picos de audio, movimiento intenso y cambios de escena. Las detecciones específicas de Warzone (por ejemplo, leer el kill feed) no están en el perfil. Serán analizadores en `plugins/` y se evaluarán después de medir la línea base.

## 11. Almacenamiento local

```
data/
├─ clipperai.db              # SQLite en modo WAL, claves externas activas
├─ runtime/sesion.token      # Token de sesión del arranque actual
├─ media/<video_id>/         # Copias gestionadas (solo si el usuario lo elige)
├─ work/<video_id>/          # Audio WAV, fotogramas, salidas por segmento: regenerable
└─ exports/<proyecto>/       # Clips MP4 y archivos SRT
```

- En la base de datos se guardan rutas relativas a `data/` para copias y ruta absoluta solo para referencias (`ruta_original`).
- Todo acceso a archivos pasa por `core/rutas.py`. Esa función resuelve la ruta y verifica que quede dentro del directorio permitido.
- Los archivos en `work/` se pueden borrar sin pérdida. Se regeneran.
- Estimación por validar con mediciones: WAV 16 kHz mono ocupa unos 115 MB por hora de audio. Los fotogramas se extraen a baja resolución y baja frecuencia, no todos los cuadros.

## 12. Modelo de datos (inicial)

- `proyectos`: id, nombre, perfil_id, formato_salida, creado.
- `videos`: implementada en la migración 0002 con id, proyecto_id, nombre, ruta_original, tamano_bytes, duracion_segundos, ancho, alto, fps, codec_video, codec_audio, formato y creado. Las columnas `modo` y `ruta_gestionada` llegarán con la copia gestionada (D-023).
- `trabajos`: id, tipo, estado, progreso, payload_json, cancelacion_solicitada, intentos, latido, error, creado, actualizado.
- `segmentos_trabajo`: id, trabajo_id, tipo_analisis, indice, inicio, fin, estado, salida_ruta, salida_tamano, version_analizador.
- `senales`: id, video_id, analizador, tipo, inicio, fin, valor (0 a 1), confianza.
- `transcripciones`: id, video_id, inicio, fin, texto, idioma.
- `candidatos`: id, video_id, perfil_id, inicio, fin, puntuacion, estado (`pendiente`, `aprobado`, `descartado`).
- `clips`: id, candidato_id, ruta_salida, formato, resolucion, subtitulos.
- `decisiones`: id, candidato_id, accion, creado. Es la base del módulo `preferences`.

## 13. Flujo de procesamiento

1. **Importar:** se registra el video (referencia o copia) y FFprobe lee sus metadatos.
2. **Preparar:** FFmpeg extrae el audio a WAV 16 kHz mono y se define la lista de segmentos.
3. **Analizar:** por cada segmento, los analizadores registrados producen señales. Se guardan con escritura atómica.
4. **Transcribir:** faster-whisper procesa el audio por segmentos.
5. **Puntuar:** `scoring` fusiona señales según el perfil activo.
6. **Proponer:** `candidates` genera intervalos sin solapamientos, con inicio y fin ajustados a la duración del perfil.
7. **Revisar:** el usuario previsualiza, ajusta cortes, aprueba o descarta. Cada decisión se guarda.
8. **Exportar:** FFmpeg renderiza los clips aprobados, con subtítulos SRT opcionales.

Cada paso es un trabajo con estado persistido, reanudable según la sección 9.

## 14. Fases de desarrollo

1. **Fundamentos:** estructura, FastAPI, token y validaciones, SQLite, resolución de herramientas, frontend Next.js con proxy seguro, e importación de videos y lectura de metadatos. Completado hasta el proxy y la interfaz inicial. La importación de videos sigue pendiente.
2. **Procesamiento:** FFmpeg, OpenCV, audio y fotogramas, cola de trabajos con recuperación.
3. **Inteligencia artificial:** faster-whisper, analizadores visuales, puntuación y perfiles `automatico` y `gaming`.
4. **Edición:** vista previa, ajuste de cortes, subtítulos y exportación.
5. **Especialización:** más perfiles, registro de preferencias y evaluación de modelos propios.

## 15. Criterio de éxito del MVP

1. Importar un video local, por referencia o copia.
2. Analizarlo con faster-whisper y OpenCV, con progreso visible y recuperación tras un cierre.
3. Proponer varios momentos interesantes con el perfil `automatico` o `gaming`.
4. Revisar los candidatos en la interfaz.
5. Exportar los clips aprobados como archivos independientes.

Todo funciona sin servicios en la nube.

## 16. Puntos abiertos

- Medición real de `small` INT8 con videos de más de una hora en el i7-1165G7. Se decide si se usa `base` a partir de esa medición.
- Formato de subtítulos de salida: SRT, subtítulos quemados, o ambos.
- Conjunto de 3 a 5 videos de prueba para evaluar la detección. Hay que reunirlo antes de medir calidad.
- Formatos de entrada admitidos. Se definen al implementar la importación.
- Evaluación de aceleración Apple Silicon (PyTorch MPS). Se hace cuando exista un equipo macOS disponible para pruebas.

## 17. Módulo 1: videos (implementado)

### 17.1 Endpoints del backend

Todos bajo `/api/v1` y protegidos por token (sección 7).

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/proyectos` | Lista los proyectos. Cada uno incluye `cantidad_videos` (D-027). |
| POST | `/proyectos` | Crea un proyecto. Cuerpo: `{"nombre": "..."}`. Responde con `cantidad_videos: 0`. |
| GET | `/videos?proyecto_id=n` | Lista los videos de un proyecto, con estado de disponibilidad. |
| POST | `/videos` | Registra un video por referencia. Cuerpo: `{"proyecto_id": n, "ruta": "..."}`. Responde 201. |
| POST | `/videos/seleccion` | Abre el selector nativo. Responde `{"ruta": "..."}` o `{"ruta": null}`. |
| GET | `/videos/{id}` | Devuelve los metadatos de un video. |
| DELETE | `/videos/{id}` | Elimina el registro. Responde 204. El archivo original no cambia. |
| GET | `/videos/{id}/stream` | Transmite el original con soporte HTTP Range (D-025). |

Códigos de error: 404 (no existe), 409 (duplicado en el proyecto), 422 (archivo o formato no válido), 501 (selector no disponible), 503 (FFprobe no disponible).

### 17.1.1 Datos de desarrollo

Los registros que existen hoy en `data/clipperai.db` (proyectos como "Prueba integral" y sus videos) son datos de desarrollo creados durante las pruebas. No son datos de usuario ni deben usarse como referencia de producción. La base se conservará hasta que se decida lo contrario, y no debe borrarse ni recrearse como parte del desarrollo normal.

### 17.2 Flujo de importación

1. El usuario elige el archivo con el selector o escribe la ruta.
2. El servicio valida la ruta (D-024), incluida la cadena de directorios padre frente a enlaces y junctions, y comprueba que el proyecto exista. La validación se repite en cada disponibilidad y en cada transmisión.
3. FFprobe devuelve los metadatos. Un fallo de lectura se rechaza con 422.
4. Se inserta la fila. Si el archivo ya estaba en el proyecto, responde 409.

### 17.3 Cobertura de pruebas

- Backend: 106 pruebas pasan en `backend/tests/` (incluye `test_conexion.py`, según D-028). Incluyen el conteo de videos por proyecto (sin videos, con uno, con varios, aislamiento entre proyectos y recuento tras eliminar). Una se omite porque Windows no permite crear enlaces simbólicos a archivos sin privilegios. Incluye las pruebas de enlaces y junctions en directorios padre.
- Cubren importación válida e inválida, rutas con espacios, tildes y caracteres especiales, archivos grandes, Range (206, 416, varios rangos), eliminación sin tocar el original, duplicados, selector simulado en Windows y macOS, y migraciones.
- Integración por el proxy con un archivo de 911 MB: 25 comprobaciones pasan. La transmisión completa se verificó aparte: el SHA256 del archivo descargado coincide con el original.

## 18. Pendientes técnicos

- **`frontend/next-env.d.ts`:** tiene cambios sin commit desde antes de la fase de proyectos. Next 16.4.6 reescribe las rutas de tipos de `.next/types/` a `.next/dev/types/` en modo desarrollo, y se regenera con cada `dev` o `build`. Pendiente: decidir si se versiona la versión regenerada o si el archivo sale de Git.
- **`frontend/tsconfig.tsbuildinfo`:** es caché incremental de `tsc` y está versionado. Cada typecheck lo modifica. Pendiente: quitarlo del seguimiento de Git (`git rm --cached` y entrada en `.gitignore`).
