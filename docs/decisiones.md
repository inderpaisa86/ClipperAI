# Registro de decisiones

Cada decisión tiene fecha, contexto, decisión y consecuencias. Una decisión nueva se agrega al final y no se borra. Si cambia, la entrada nueva indica cuál reemplaza.

---

## D-001. Stack principal
**Fecha:** sesión inicial
**Estado:** Aprobada

**Contexto.** ClipperAI es una aplicación local para Windows con procesamiento de video y transcripción.

**Decisión.** Next.js para el frontend. Python 3.12 con FastAPI para el backend. FFmpeg y FFprobe para multimedia. OpenCV para visión. faster-whisper para transcripción. SQLite para datos. PyTorch se incorpora en una fase posterior.

**Consecuencias.** La comunicación es REST sobre localhost. Los modelos se sustituyen mediante interfaces.

---

## D-002. Transcripción con faster-whisper
**Fecha:** sesión de decisiones técnicas
**Estado:** Aprobada

**Decisión.** Usar faster-whisper en lugar de la implementación original de Whisper. Modelo inicial `small`, CPU, cuantización INT8. El modelo se configura y puede cambiarse a `base` sin modificar código.

**Consecuencias.** Se mide el rendimiento con videos reales antes de confirmar el modelo.

---

## D-003. Visión sin Deep Learning en el MVP
**Fecha:** sesión de decisiones técnicas
**Estado:** Aprobada

**Decisión.** El MVP usa OpenCV con heurísticas: cambios de escena, movimiento, brillo y fotogramas representativos. Los analizadores se conectan mediante una interfaz común para incorporar modelos de Deep Learning después.

---

## D-004. Motor de selección multiseñal
**Fecha:** sesión de decisiones técnicas
**Estado:** Aprobada

**Decisión.** El motor combina señales audiovisuales. No depende de una sola técnica. Los analizadores se agregan sin modificar el núcleo.

---

## D-005. Producto universal con perfiles configurables
**Fecha:** sesión de decisiones técnicas
**Estado:** Aprobada, con ajuste en D-011

**Decisión.** ClipperAI no se limita a videojuegos. Los perfiles son configuración sobre un motor común.

---

## D-006. Hardware sin CUDA
**Fecha:** sesión de decisiones técnicas
**Estado:** Aprobada

**Decisión.** Optimizar para Intel Core i7-1165G7, 15,6 GB de RAM e Intel Iris Xe. No asumir CUDA ni GPU NVIDIA. Un trabajo pesado a la vez.

---

## D-007. Importación por referencia con copia opcional
**Fecha:** revisión de arquitectura
**Estado:** Aprobada

**Decisión.** Por defecto, la base de datos guarda la ruta original y el video no se duplica. El usuario puede elegir copiar el video a `data/media/`, en cuyo caso ClipperAI gestiona la copia.

**Consecuencias.** Hay que validar que el archivo original exista antes de procesarlo. Si se mueve o elimina, el video queda marcado como no disponible.

---

## D-008. Cola de trabajos en SQLite
**Fecha:** revisión de arquitectura
**Estado:** Aprobada

**Decisión.** La cola vive en SQLite con un worker propio. No se usan Celery ni Redis. Una tarea pesada a la vez, con progreso, cancelación y recuperación.

**Consecuencias.** Se evita un servicio adicional en Windows. El worker debe cuidar la recuperación explícitamente (ver `arquitectura.md`, sección 8).

---

## D-009. Gestor de dependencias Python con uv
**Fecha:** revisión de arquitectura
**Estado:** Aprobada. Instalación de uv y entorno del backend autorizados para la Fase 1.

**Decisión.** Usar uv con entorno virtual y archivo de bloqueo `uv.lock`.

---

## D-010. Progreso por polling
**Fecha:** revisión de arquitectura
**Estado:** Aprobada

**Decisión.** El frontend consulta el estado de los trabajos cada 2 segundos. SSE se evalúa después si hace falta más fluidez.

---

## D-011. Perfiles como datos, no como lista cerrada
**Fecha:** revisión de arquitectura
**Estado:** Aprobada. Reemplaza la lista de siete perfiles de la versión 1.0 del documento de arquitectura.

**Decisión.** Un perfil es un archivo JSON validado en `backend/app/perfiles/`. No existe una lista cerrada de perfiles. Para el MVP se incluyen `automatico` y `gaming`. `gaming` es el primer escenario de pruebas, con Warzone.

**Consecuencias.** Agregar un perfil no requiere cambios de código. Las detecciones específicas de un juego van en `plugins/` y no en el perfil.

---

## D-012. Organización del backend por dominio
**Fecha:** revisión de arquitectura
**Estado:** Aprobada

**Decisión.** Los módulos se organizan en `backend/app/modules/`. Un módulo no accede a las tablas de otro módulo y usa su servicio.

---

## D-013. Selección de archivos sin multipart
**Fecha:** revisión de arquitectura
**Estado:** Aprobada

**Decisión.** No se suben videos por `multipart`. La importación recibe una ruta, escrita por el usuario o elegida con un diálogo nativo abierto por el backend, y la valida.

---

## D-014. Seguridad de la API local
**Fecha:** revisión de arquitectura
**Estado:** Aprobada. Entrega del token confirmada mediante proxy de Next.js. La generación del token la hace el backend (ver D-018).

**Decisión.** La API valida `Origin` y `Host`, y exige un token de sesión por cabecera en todos los endpoints `/api/v1`. El token se genera en cada arranque y se entrega al servidor de Next.js, que lo usa en un proxy. El navegador no recibe el token.

**Confirmado.** El proxy de Next.js se prefiere frente a una cookie `httpOnly`, porque el token nunca llega al código que corre en el navegador.

---

## D-015. Recuperación por segmentos
**Fecha:** revisión de arquitectura
**Estado:** Aprobada

**Decisión.** El análisis se divide en segmentos con estado persistido. Las salidas se escriben de forma atómica. Al arrancar, solo se omiten los segmentos completados cuya salida existe, tiene el tamaño esperado y su versión de analizador sigue vigente.

---

## D-016. Módulos y archivos creados bajo demanda
**Fecha:** revisión de arquitectura
**Estado:** Aprobada

**Decisión.** No se crean archivos vacíos. Cada módulo incluye `router.py`, `service.py`, `repository.py` y `schemas.py` solo cuando la lógica los requiere.

---

## D-017. Compatibilidad multiplataforma
**Fecha:** revisión de Fase 1
**Estado:** Aprobada. El desarrollo inicial sigue en Windows. macOS no se instala ni se prueba todavía.

**Contexto.** ClipperAI debe poder ejecutarse en el futuro en Windows 10/11, macOS Intel y macOS Apple Silicon sin cambiar la arquitectura principal.

**Decisión.**

1. Plataformas objetivo: Windows 10/11 x64, macOS Intel (x86_64) y macOS Apple Silicon (arm64).
2. Todo acceso a archivos usa `pathlib`. No hay rutas absolutas ni letras de unidad en el código.
3. La configuración de rutas procede de variables de entorno (`CLIPPERAI_DATA_DIR`, `CLIPPERAI_FFMPEG`, `CLIPPERAI_FFPROBE`) o de valores por defecto relativos al repositorio.
4. `core/plataforma.py` detecta sistema operativo y arquitectura. Las decisiones que dependen de la plataforma se toman a partir de esa detección.
5. FFmpeg y FFprobe se resuelven en este orden: ruta configurada, luego `shutil.which`, y si ninguna funciona, un error con la instrucción de instalación de esa plataforma.
6. La aceleración por hardware se detecta en tiempo de ejecución consultando las capacidades de FFmpeg. No se fija por sistema operativo. Ejemplos: `h264_qsv` en Intel, `h264_videotoolbox` en macOS. Si no hay aceleración, se usa `libx264`.
7. Hay un script de arranque por plataforma: `scripts/arrancar_windows.ps1` y `scripts/arrancar_macos.sh`. Ambos solo inician el backend y el frontend, sin lógica de negocio.
8. No se usan dependencias exclusivas de Windows ni de NVIDIA. `uv.lock` resuelve para todas las plataformas.
9. Next.js, FastAPI y SQLite no tienen dependencias de sistema operativo.
10. Los scripts `.sh` usan finales de línea LF y los `.ps1` usan CRLF, según `.gitattributes`.
11. El archivo de token se crea con permisos restringidos en POSIX (`chmod 600`). En Windows se confía en los permisos del perfil de usuario, y se documenta esa limitación.
12. Las pruebas no dependen de rutas fijas. Usan directorios temporales.

**Apple Silicon (para fases futuras).** PyTorch puede usar el backend MPS en lugar de CPU. faster-whisper se basa en CTranslate2, que no usa Metal. La decisión sobre su aceleración se toma al probar en macOS.

**Consecuencias.** Cualquier cambio que introduzca una ruta de Windows, una llamada específica de Windows o una dependencia de CUDA debe rechazarse en revisión.

---

## D-018. El backend genera el token de sesión
**Fecha:** revisión de Fase 1
**Estado:** Aprobada. Modifica el punto 3 de la sección 7 de `arquitectura.md`.

**Decisión.** El backend genera el token al arrancar y lo escribe en `data/runtime/sesion.token`. Los scripts de arranque no generan el token.

**Motivo.** Un único generador de token funciona igual en cualquier plataforma. Evita duplicar la lógica en PowerShell y en shell.

---

## D-019. Autorización de la Fase 1
**Fecha:** revisión de Fase 1
**Estado:** Aprobada por el usuario. Superada en su parte de frontend por D-020.

**Decisión.** Se autoriza instalar uv con winget, crear el entorno virtual del backend y instalar sus dependencias de Fase 1: FastAPI, Uvicorn, Pydantic Settings, Pytest y HTTPX. No se instalan OpenCV, faster-whisper ni PyTorch hasta sus fases.

---

## D-020. Frontend Next.js y dependencias npm
**Fecha:** revisión de Fase 1
**Estado:** Aprobada por el usuario.

**Decisión.**

- Se autoriza instalar las dependencias npm del frontend.
- Versiones: Next.js 16.4.6 con App Router, React 19.3.1, TypeScript 5.9.3, ESLint con `eslint-config-next`.
- TypeScript se fija en la rama 5. La rama 7 existe, pero Next.js documenta soporte para la 5.
- No se incorpora ninguna librería de interfaz, gráficos ni edición de video. La interfaz usa CSS propio.
- El frontend usa el puerto 3000 y se enlaza a `127.0.0.1`.
- El estado del backend se consulta cada 2 segundos, según D-010.

**Consecuencias.** Cualquier librería de interfaz, gráficos o edición debe justificarse y pedirse por separado.

---

## D-021. Proxy del frontend con lista blanca y validaciones propias
**Fecha:** revisión de Fase 1
**Estado:** Aprobada por el usuario.

**Decisión.**

- El navegador solo llama a `/api/backend/*`. El Route Handler de Next.js reenvía al backend y añade el token.
- El token se lee del archivo de sesión en cada petición. No se cachea, porque cambia con cada arranque del backend.
- El proxy valida `Host`, `Origin` y `Sec-Fetch-Site` antes de reenviar. El backend también valida `Host` y `Origin`.
- Los destinos se listan explícitamente en `lib/proxy/destinos.ts`. Solo `GET salud` está permitido.
- Las variables de entorno del servidor no usan el prefijo `NEXT_PUBLIC_`.

**Motivo.** Sin validación en el proxy, cualquier equipo que alcance el servidor de Next.js podría usar el token indirectamente. El proxy es la única frontera del token, por eso se valida en ambos lados.

**Consecuencias.** Un endpoint nuevo requiere una entrada en la lista blanca y una decisión registrada. Las pruebas de integración de este registro se ejecutaron con `curl` y Microsoft Edge en modo headless.

---

## D-022. Selector nativo de archivos con respaldo de ruta escrita
**Fecha:** Módulo 1 (videos)
**Estado:** Aprobada por el usuario.

**Decisión.**

- El backend abre el selector del sistema desde `POST /api/v1/videos/seleccion`. En Windows usa `powershell.exe` con `System.Windows.Forms.OpenFileDialog`. En macOS usa `osascript` con `choose file`.
- Los comandos se construyen con listas de argumentos. En Windows el script se pasa en base64 con `-EncodedCommand`. Ningún dato del cliente entra en el comando.
- Solo puede haber un selector abierto a la vez. Un segundo intento responde 409. El tiempo máximo de espera es de 10 minutos.
- Si el usuario cancela, la respuesta es `{"ruta": null}`.
- El lugar de las ramas por sistema operativo es `core/dialogo_archivos.py`, además de `core/plataforma.py` y `core/herramientas.py`.
- En sistemas sin soporte, el endpoint responde 501. La interfaz ofrece siempre el campo para escribir la ruta.

**Limitación.** El diálogo no se puede probar sin interacción humana. Las pruebas automáticas simulan el proceso del sistema.

---

## D-023. Esquema SQLite inicial con migraciones versionadas
**Fecha:** Módulo 1 (videos)
**Estado:** Aprobada por el usuario.

**Decisión.**

- Las migraciones son archivos `NNNN_nombre.sql` en `backend/app/db/migraciones/`. La versión se guarda en `PRAGMA user_version`. Cada migración corre en una transacción junto con la actualización de su versión.
- `0001_proyectos.sql` crea `proyectos`. `0002_videos.sql` crea `videos`.
- En `videos`, `proyecto_id` es obligatorio y usa `ON DELETE RESTRICT`. La restricción `UNIQUE (proyecto_id, ruta_original)` impide registrar dos veces el mismo archivo en un proyecto, pero permite registrarlo en proyectos distintos.
- La columna `modo` y la columna `ruta_gestionada` de la versión 1.4 de la arquitectura no se crean todavía. Llegarán con la copia gestionada, que es una fase posterior.
- Cada módulo accede solo a sus tablas. `videos` valida el proyecto a través de `projects.service`.

**Consecuencias.** Cambiar el esquema requiere una migración nueva. No se editan migraciones ya aplicadas.

---

## D-024. Importación por referencia y validación del archivo
**Fecha:** Módulo 1 (videos)
**Estado:** Aprobada por el usuario. Modifica la frase sobre "directorios permitidos" de la sección 6 de `arquitectura.md`.

**Decisión.** Una referencia puede apuntar a cualquier ubicación que el usuario elija. El control se hace sobre el archivo, no sobre el directorio. Cada importación valida:

1. Ruta absoluta, sin byte nulo, de longitud máxima de 4096 caracteres.
2. Extensión admitida: `.mp4`, `.m4v`, `.mov`, `.mkv`, `.webm`, `.avi`.
3. El archivo existe, no es un enlace simbólico, no es un directorio y no está vacío.
4. Se puede abrir para lectura.
5. FFprobe lo lee y contiene una pista de video. Una carátula adjunta no cuenta como pista de video.

El archivo original nunca se copia, modifica ni elimina. Eliminar un video borra solo su fila en SQLite.

Si el original se mueve o se borra después de importarlo, el video aparece como no disponible. El registro se conserva.

**Revisión (tras validación manual del Módulo 1).** La comprobación original solo miraba el último componente de la ruta, y la disponibilidad y la transmisión seguían enlaces con `is_file()`. Esto permitía que un directorio intermedio convertido en enlace o junction (Windows) redirigiera la lectura a otro archivo. Se corrigió así:

- Se rechaza cualquier ruta con `..`.
- Se rechaza la ruta si ella misma o cualquier directorio padre es un enlace simbólico o un junction (`_contiene_enlaces`).
- La disponibilidad y la transmisión revalidan la ruta en cada uso (`_archivo_accesible`). Un enlace creado después de importar deja el video como no disponible y la transmisión responde 404.

**Consecuencias.** Las rutas que pasan por un enlace legítimo del sistema operativo también se rechazan. En macOS, por ejemplo, `/var` y `/tmp` son enlaces hacia `/private`. El selector nativo devuelve rutas reales, así que el caso normal no se ve afectado. Las pruebas cubren junctions (Windows) y enlaces a directorios (POSIX). Los enlaces a archivos siguen omitiéndose en Windows sin privilegios.

---

## D-025. Transmisión de video con HTTP Range propio
**Fecha:** Módulo 1 (videos)
**Estado:** Aprobada por el usuario.

**Decisión.**

- `GET /api/v1/videos/{id}/stream` responde 200 sin cabecera `Range`, 206 con un rango válido y 416 con un rango fuera del archivo o mal formado.
- Se admiten rangos `bytes=i-f`, `bytes=i-` y `bytes=-n`. Con varios rangos se sirve el archivo completo con 200.
- El archivo se lee en bloques de 1 MiB. Ningún paso carga el video completo en memoria.
- La respuesta lleva `Accept-Ranges: bytes`, `Content-Range` y `Cache-Control: no-store`.
- El tipo MIME sale de la extensión.

**Motivo.** `FileResponse` de Starlette no garantiza el manejo completo de rangos en todas sus versiones. Con un parser propio el comportamiento queda cubierto por pruebas.

---

## D-026. Ampliación del proxy: escritura, parámetros y límites
**Fecha:** Módulo 1 (videos)
**Estado:** Aprobada por el usuario. Amplía D-021.

**Decisión.**

- Métodos permitidos por destino: `GET`, `POST` y `DELETE`. Cada entrada de la lista blanca declara su método.
- Las peticiones que no son `GET` deben llegar con cabecera `Origin` permitida. Así se bloquea CSRF desde otras páginas.
- Los parámetros de consulta se validan por destino. Hoy solo `proyecto_id` en `GET /videos`, con enteros positivos. Cualquier otro parámetro responde 400.
- Los cuerpos `POST` deben ser `application/json` y pesan como máximo 64 KB. Más de eso responde 413. Un tipo distinto responde 415.
- Los archivos de video nunca pasan por el proxy como cuerpo de una petición. Solo la transmisión de salida viaja por el proxy, como flujo.

**Consecuencias.** Un endpoint nuevo con escritura o parámetros requiere su entrada en `lib/proxy/destinos.ts`.

---

## D-027. Conteo de videos por proyecto mediante servicio público de videos
**Fecha:** Mejora de proyectos y navegación
**Estado:** Aprobada por el usuario (opción A).

**Contexto.** La lista de proyectos necesita mostrar cuántos videos tiene cada uno. El dato vive en la tabla `videos`, que pertenece al módulo `videos`. D-012 prohíbe que `projects` lea esa tabla.

**Decisión.**

- `GET /api/v1/proyectos` y `POST /api/v1/proyectos` devuelven el campo `cantidad_videos` (entero, cero si el proyecto no tiene videos).
- `projects.service` obtiene el conteo llamando a dos funciones públicas de `videos.service`: `contar_por_proyecto` (un proyecto) y `contar_por_proyectos` (un diccionario con todos los proyectos, en una sola consulta). `projects.repository` no referencia la tabla `videos`.
- `videos.repository` ejecuta las consultas `COUNT`. Solo `videos` accede a su tabla.
- La dependencia entre los dos módulos es circular a nivel de importación (`videos.service` ya usaba `projects.service` para validar el proyecto). Se resuelve importando el módulo completo (`from app.modules.videos import service as videos`) y usando sus funciones solo en tiempo de llamada.

**Alternativas descartadas.**

- Que `projects` consulte `SELECT ... FROM videos`. Rompe D-012.
- Que el frontend pida los videos de cada proyecto para contarlos. Obliga a una petición por proyecto.

**Consecuencias.** El cambio es aditivo: no hay migración ni cambios en los datos existentes. Si algún día el conteo necesita filtrar por disponibilidad del archivo, esa lógica va en `videos.service`, no en `projects`.

---

## D-028. Conexiones SQLite por petición sin afinidad de hilo
**Fecha:** Corrección de estabilidad de la API
**Estado:** Aprobada por el usuario.

**Contexto.** La dependencia `obtener_conexion` es un generador síncrono. FastAPI ejecuta su parte de apertura y la de cierre en hilos del pool, que pueden ser distintos. Con `sqlite3` por defecto, el cierre en otro hilo lanza `ProgrammingError` y la petición responde 500. El fallo era intermitente y afectaba a todos los endpoints con la dependencia, incluido `GET /api/v1/proyectos`.

**Decisión.**

- `conectar` abre la conexión con `check_same_thread=False`.
- Invariante: cada conexión tiene un único dueño a la vez. Una petición crea su conexión, la usa y la cierra. Ninguna conexión se comparte entre peticiones ni se usa desde dos hilos simultáneamente.
- El endpoint de transmisión (`/stream`) solo usa la conexión antes de responder. El flujo posterior lee el archivo sin base de datos.

**Alternativas descartadas.**

- Convertir los endpoints a `async`. Obliga a reescribir todos los accesos y no evita la afinidad de hilo del cierre.
- Un pool de conexiones compartido. No hace falta para una aplicación local de un solo usuario y añade estado compartido.

**Consecuencias.** Un cambio futuro que comparta una conexión entre peticiones o entre hilos a la vez rompe el invariante. `backend/tests/test_conexion.py` reproduce el fallo original (crear y cerrar en hilos distintos, usar la conexión desde otro hilo) y verifica el cierre también ante errores.

---

## D-029. Cola de trabajos en SQLite con proceso hijo por trabajo
**Fecha:** Módulo 2, Etapa 0
**Estado:** Aprobada por el usuario. Implementación en la Etapa 1.

**Contexto.** La arquitectura situaba la cola en la Fase 2, pero no existía. Es prerrequisito del análisis de audio y video.

**Decisión.**

- Tablas `trabajos` y `segmentos_trabajo` en la migración 0003. Estados según la arquitectura, sección 9.1.
- **Reclamo atómico.** El worker toma un trabajo con `BEGIN IMMEDIATE` y `UPDATE ... WHERE id = ? AND estado = 'en_cola'`. Solo cuenta si la actualización afecta una fila. Al reclamar, guarda un `claim_token` (UUID aleatorio), el PID del proceso hijo y su hora de creación.
- **Token de ejecución (fencing).** Toda actualización de `trabajos` o `segmentos_trabajo` exige el `claim_token` vigente. Un proceso que perdió su reclamo no puede confirmar resultados.
- **Un trabajo pesado a la vez.** El worker reclama de a uno. Además, mantiene un bloqueo exclusivo del sistema operativo sobre `data/runtime/worker.lock`, para que dos instancias del backend no ejecuten trabajos a la vez. El bloqueo se implementa en `core/plataforma.py`.
- **Recuperación.** Antes de devolver un trabajo a `en_cola`, el sistema termina el proceso registrado. Verifica antes el PID y la hora de creación, para no matar un proceso reutilizado por el sistema. Si no logra terminarlo, el trabajo pasa a `fallido` con un error controlado y no se reasigna.
- **Gestión de procesos.** En Windows, el proceso hijo y su FFmpeg se asocian a un Job Object con `KILL_ON_JOB_CLOSE`, de modo que el cierre del padre los termina. En macOS y Linux se usa un grupo de procesos (`start_new_session` y `killpg`). Ambas implementaciones quedan detrás de `core/plataforma.py`.
- **Cancelación.** La API marca `cancelacion_solicitada`. El proceso hijo la revisa cada 10 segundos de video procesado o al cerrar cada bloque, no solo entre segmentos.
- **Latido.** El hijo actualiza `latido` cada 10 segundos. Un latido de más de 60 segundos se considera perdido.

**Alternativas descartadas.**

- Ejecutar el análisis en un hilo del proceso de la API. La memoria no se libera al terminar y un fallo de FFmpeg puede afectar a la API.
- Confiar solo en el estado de la base de datos, sin token de ejecución. Un proceso zombi podría confirmar resultados después de que otro proceso reasignó el trabajo.

**Consecuencias.** La garantía de no ejecución doble tiene tres capas: el reclamo atómico, el bloqueo del worker y el token. Un cambio que omita cualquiera de ellas rompe la garantía.

---

## D-030. Audio mediante tubería PCM sin WAV persistente
**Fecha:** Módulo 2, Etapa 0
**Estado:** Aprobada por el usuario.

**Decisión.**

- FFmpeg entrega PCM `s16le`, mono, 16 kHz, por la salida estándar. Python lee bloques de 1 MiB y calcula la energía RMS en ventanas de 200 ms.
- No se escribe WAV. Si la Fase 3 necesita WAV para faster-whisper, se genera entonces.
- Los silencios y la actividad se derivan de la serie de energía en un paso de consolidación al final, cuando ya están todos los segmentos. Así el umbral usa el video completo.
- Las invocaciones de FFmpeg usan `-nostdin`, `-protocol_whitelist file,pipe` y lista de argumentos. El stderr se escribe en un archivo temporal con tamaño máximo, para que nunca bloquee la tubería.

**Medición (Etapa 0).** Clip sintético de 120 s, 1080p, 60 fps. Audio completo en 0,15 s con 8 hilos. Cálculo estimado para una hora: unos 5 s.

---

## D-031. Video decodificado por FFmpeg y analizado con OpenCV
**Fecha:** Módulo 2, Etapa 0
**Estado:** Aprobada por el usuario.

**Decisión.**

- FFmpeg decodifica, reduce la tasa a 4 fps y escala a 320×180 en gris (rawvideo por tubería). OpenCV analiza en 160×90 y calcula escenas, movimiento y brillo.
- Se descarta `cv2.VideoCapture`. En Windows no maneja bien las rutas no ASCII, y no permite controlar la escala ni la tasa de muestreo durante la decodificación.
- Las miniaturas se codifican con `cv2.imencode` y se escriben con `pathlib`, no con `cv2.imwrite`, que falla con rutas no ASCII en Windows.
- Hilos de FFmpeg configurables. El valor por defecto se fija con la medición de la Etapa 0 y no se asume.
- La decodificación por hardware (QSV) no se usa en esta fase. En la medición fue más lenta (28,1 s frente a 15,5 s por CPU), porque obliga a descargar los fotogramas a memoria del sistema. Se revisa en otra fase con otra medición.

**Medición (Etapa 0).** Mismo clip de 120 s. Tiempo del flujo de video completo: 8,7 s con 8 hilos, 15,0 s con 4 y 21,8 s con 2. Decodificación sola con 4 hilos: 15,5 s. Con 4 hilos, el pico de memoria del FFmpeg hijo fue de 81 MB. El pico del proceso Python fue de 40 MB con 8 hilos, incluidos NumPy y OpenCV.

---

## D-032. Confirmación por segmento y recuperación de miniaturas
**Fecha:** Módulo 2, Etapa 0. Revisada a petición del usuario.
**Estado:** Aprobada por el usuario. Reemplaza, solo para señales y fotogramas, la verificación por archivo de salida de D-015.

**Decisión.** Secuencia por segmento:

1. Commit: el segmento pasa a `procesando` con el `claim_token`.
2. Análisis del segmento, sin escritura en base de datos.
3. Cada miniatura se escribe en `*.tmp` y se renombra con `os.replace`. El nombre es determinista: `data/work/<video_id>/fotogramas/<tiempo_ms>.jpg`.
4. Una sola transacción inserta las señales y las filas de `fotogramas`, y marca el segmento como `completado`. Verifica el `claim_token` en esa misma transacción.

**Recuperación cuando la miniatura existe, pero la transacción no llegó a confirmarse.**

- SQLite confirma o descarta la transacción completa. Nunca quedan señales ni filas parciales.
- El segmento sigue en `procesando`. Al recuperar, vuelve a `pendiente` y se reprocesa.
- Si el reprocesamiento genera un fotograma con el mismo `tiempo_ms`, sobrescribe el archivo anterior.
- Un archivo que quedó sin fila asociada se borra en un barrido previo a cada análisis del video. El barrido elimina en `data/work/<video_id>/fotogramas/` los archivos que no tienen fila en `fotogramas`. Solo corre cuando no hay otro trabajo activo, porque un único trabajo pesado está en ejecución a la vez (D-029).
- Si la confirmación falla por una excepción de Python, el proceso borra en su mismo flujo las miniaturas que escribió en ese segmento. Es un intento de limpieza, no una garantía. El barrido es la garantía.
- Al recuperar, un segmento `completado` se verifica contra sus filas. Si falta un archivo referenciado, el segmento vuelve a `pendiente`.

**Consecuencias.** La base de datos es el punto de verdad. Un archivo huérfano ocupa espacio hasta el siguiente barrido, pero nunca aparece en la API.

---

## D-033. Tiempos en milisegundos enteros
**Fecha:** Módulo 2, Etapa 0
**Estado:** Aprobada por el usuario.

**Decisión.** Los campos `inicio_ms`, `fin_ms` y `tiempo_ms` son enteros en SQLite y en la API. La arquitectura no fijaba unidad. Los enteros evitan errores de redondeo al comparar intervalos y al unir segmentos.

---

## D-034. Módulo `analisis` como dueño de sus datos
**Fecha:** Módulo 2, Etapa 0
**Estado:** Aprobada por el usuario.

**Decisión.**

- `modules/analisis/` es dueño de las tablas `analisis`, `senales` y `fotogramas`. Su migración es la 0004.
- `modules/audio/` y `modules/vision/` no tienen tablas, router ni repositorio. Implementan el contrato de `plugins/` y devuelven señales. Solo `analisis` escribe en la base de datos (D-012).
- `senales` referencia `analisis_id` en lugar de guardar el nombre del analizador. Así cada señal pertenece a una versión concreta del análisis.
- Clave `UNIQUE (video_id, analizador)` en `analisis`.
- Las claves externas con `ON DELETE CASCADE` son red de seguridad. El borrado real pasa por `analisis.service`, que también elimina archivos de `data/work/`.

---

## D-035. Dependencias de análisis: OpenCV headless y NumPy
**Fecha:** Módulo 2, Etapa 0
**Estado:** Aprobada por el usuario. Instalada en Etapa 0.

**Decisión.**

- Se agregan `opencv-python-headless` (5.1.0.95) y `numpy` (2.5.5) a `backend/pyproject.toml`. El lock queda en `backend/uv.lock`.
- No se instalan PyTorch ni faster-whisper en este módulo.
- No hay dependencias CUDA ni NVIDIA en el lock. El build de OpenCV reporta OpenCL, pero no CUDA.

**Verificado en Etapa 0.**

- `uv lock --check` pasa.
- Las ruedas incluyen Windows x64 (`win_amd64`), macOS arm64 (`macosx_15_0_arm64`) y macOS x86_64 (`macosx_15_0_x86_64`).
- La suite existente pasa completa: 106 pruebas, con 1 omitida por el enlace simbólico sin privilegios.

**Riesgo abierto.** Las ruedas de OpenCV para macOS requieren macOS 15 o posterior. Un Mac Intel con una versión anterior no tendrá rueda y uv intentaría compilar desde el código fuente. Eso no está verificado y bloquea el soporte de macOS Intel en este módulo. Se verifica cuando exista un equipo macOS disponible (D-017).

---

## D-036. Ampliación del proxy para análisis
**Fecha:** Módulo 2, Etapa 0
**Estado:** Aprobada por el usuario. Amplía D-026.

**Decisión.**

- Los parámetros `inicio_ms`, `fin_ms` y `limite` aceptan enteros mayores o iguales a cero. D-026 solo admitía positivos.
- El parámetro `tipo` tiene una lista cerrada de valores admitidos, que se valida en `lib/proxy/destinos.ts`.
- Las respuestas de imagen (`image/jpeg`) se reenvían solo para el destino de miniaturas. La lista blanca fija ese tipo de contenido para ese destino.
- Cada endpoint nuevo tiene su entrada en la lista blanca, con método y parámetros explícitos.

---

## D-037. Worker en el proceso de la API con bloqueo exclusivo
**Fecha:** Módulo 2, Etapa 1
**Estado:** Aprobada por el usuario al autorizar la Etapa 1.

**Decisión.**

- El worker es un hilo que el ciclo de vida de la aplicación arranca después de las migraciones. Se controla con `Configuracion.iniciar_trabajos` (por defecto activo). Las pruebas del cliente HTTP lo desactivan.
- Antes de ejecutar nada, el worker adquiere `data/runtime/worker.lock` con `plataforma.BloqueoExclusivo`: `msvcrt.locking` en Windows y `fcntl.flock` en POSIX. Si el bloqueo está ocupado, el proceso no ejecuta trabajos.
- El sistema operativo libera el bloqueo cuando el proceso termina, también ante una caída.
- Los trabajos pesados se ejecutan en procesos hijos (D-040). El worker solo supervisa, así que el hilo no realiza cálculo pesado.
- Los tipos `diagnostico_*` existen para verificar la infraestructura. No se pueden crear desde la API. Solo `service.crear`, llamado desde código del servidor, crea trabajos.

**Alternativa descartada.** Un worker en proceso separado. Añade gestión de procesos, y el trabajo pesado ya corre en un hijo.

---

## D-038. Reclamo atómico, token de ejecución e invariante de un trabajo activo
**Fecha:** Módulo 2, Etapa 1
**Estado:** Aprobada por el usuario al autorizar la Etapa 1.

**Decisión.**

- El reclamo se hace con `BEGIN IMMEDIATE` y un `UPDATE` condicionado a `estado = 'en_cola'` y a que no exista otro trabajo `ejecutando`. Solo cuenta si la actualización afecta una fila.
- Cada ejecución recibe un `claim_token` aleatorio de 128 bits. Latidos, progreso, confirmaciones de segmento, completado, fallo, cancelación y reencolado exigen ese token. Si no coincide, lanzan `ReclamoPerdido`.
- La tabla tiene un `CHECK` que relaciona `estado = 'ejecutando'` con `claim_token IS NOT NULL`. Una fila inconsistente no se puede guardar.
- Las pruebas cubren reclamo concurrente con ocho hilos, la imposibilidad de tener dos trabajos ejecutándose, y el rechazo de un token ajeno.

---

## D-039. Identidad de procesos y terminación verificada
**Fecha:** Módulo 2, Etapa 1
**Estado:** Aprobada por el usuario al autorizar la Etapa 1.

**Decisión.**

- La identidad de un proceso es su PID más su hora de creación. En Windows se lee con `GetProcessTimes`. En POSIX se lee con `ps -o lstart=` y `LC_ALL=C`.
- Un proceso solo se termina si su identidad actual coincide con la registrada. Si el PID se reutilizó, no se toca.
- En Windows, los descendientes se terminan solo si su hora de creación es igual o posterior a la del proceso raíz.
- El proceso hijo se registra a sí mismo con `os.getpid()`. En Windows, el intérprete de `venv` es un lanzador que crea el intérprete real como hijo, así que registrar el PID del lanzador daría una identidad incorrecta.
- Un trabajo sin PID registrado no se termina ni se reencola hasta que su latido supere el umbral de 60 s (D-042).

---

## D-040. Gestión de procesos con Job Objects y grupos de procesos
**Fecha:** Módulo 2, Etapa 1
**Estado:** Aprobada por el usuario al autorizar la Etapa 1. La rama POSIX no se ha verificado en macOS ni en Linux.

**Decisión.**

- **Windows.** El proceso hijo se crea con `CREATE_SUSPENDED | CREATE_NO_WINDOW`. Después se asigna a un Job Object con `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, y se reanudan sus hilos. Cuando se cierra el último handle del job, el sistema termina todo lo que contiene. Si el backend cae, el sistema cierra el job y los procesos hijos desaparecen.
- **POSIX.** El proceso se lanza con `start_new_session=True`. El grupo se termina con `os.killpg` y `SIGKILL`.
- Al terminar un trabajo, el grupo se cierra: cualquier descendiente que siga vivo se termina. Así no quedan procesos huérfanos.
- Un proceso hijo que pierde su reclamo o que detecta que su padre ya no existe se termina con `os._exit`. En POSIX también mata su grupo.
- Toda la lógica del sistema operativo está en `core/plataforma.py`, según D-017.

---

## D-041. Cancelación idempotente y confirmaciones bloqueadas
**Fecha:** Módulo 2, Etapa 1
**Estado:** Aprobada por el usuario al autorizar la Etapa 1.

**Decisión.**

- Un trabajo en cola pasa a `cancelado`. Un trabajo en ejecución recibe `cancelacion_solicitada = 1`. Un trabajo en estado final no cambia.
- El proceso hijo detecta la cancelación en su latido (cada 10 s) o en cada verificación de su tarea. El worker también la vigila: si el hijo no sale en 15 s, termina el grupo.
- Completar un trabajo y confirmar un segmento exigen `cancelacion_solicitada = 0`. Un resultado tardío de un trabajo cancelado no se escribe.
- Cancelar dos veces produce el mismo resultado.

---

## D-042. Recuperación de trabajos interrumpidos
**Fecha:** Módulo 2, Etapa 1
**Estado:** Aprobada por el usuario al autorizar la Etapa 1.

**Decisión.**

- La recuperación corre al arrancar y cada 10 s cuando el worker está inactivo.
- Si el trabajo tiene PID e identidad registrados y el proceso sigue vivo, se termina primero. Si no logra terminarse, el trabajo se deja como está y se registra el error.
- Si el PID ya no existe o la identidad cambió, el trabajo se reencola de inmediato, siempre con el token observado.
- Si no hay PID registrado, el trabajo se reencola solo cuando su latido supera 60 s.
- Un trabajo con cancelación pendiente pasa a `cancelado`. Uno que ya se interrumpió 3 veces pasa a `fallido`.
- Los segmentos en `procesando` vuelven a `pendiente` al reencolar, o pasan a `fallido` si el trabajo termina.
- Al detener el backend de forma ordenada, el trabajo en curso vuelve a cola con `intentos` revertido en uno, porque el intento reclamado no llegó a ejecutarse. El `claim_token` se invalida y el segmento en `procesando` vuelve a `pendiente`. La parada no se evalúa contra el límite de intentos.
- Un fallo de la tarea o un proceso que termina sin confirmar consumen el intento. La recuperación de un proceso muerto también lo conserva.

---

## D-043. FFprobe con restricción de protocolos
**Fecha:** Módulo 2, Etapa 1
**Estado:** Aprobada por el usuario. Amplía D-024 en la parte de seguridad del Módulo 1.

**Decisión.** Cada invocación de FFprobe usa `-protocol_whitelist file`. Así un nombre con esquema, como `concat:` o `http:`, no puede leer otra fuente. Las pruebas comprueban que el argumento está antes de `-i` y que la lectura de un archivo local sigue funcionando.

---

## D-044. Persistencia de análisis y confirmación compartida con la cola
**Fecha:** Módulo 2, Etapa 2
**Estado:** Aprobada por el usuario al autorizar la Etapa 2.

**Contexto.** D-034 asigna al módulo `analisis` sus tablas, y D-032 exige que las señales, las filas de fotogramas y el estado del segmento se confirmen en una sola transacción. `jobs` es dueño de `segmentos_trabajo`, así que ningún módulo puede escribir en las tablas del otro.

**Decisión.**

- Migración `0004_analisis.sql` con tres tablas:
  - `analisis`: una fila por video y analizador (`UNIQUE (video_id, analizador)`), con `estado` (`pendiente`, `en_curso`, `completado`, `fallido`), `version_analizador`, `trabajo_id` y `error` (500 caracteres como máximo).
  - `senales`: `tipo`, `inicio_ms`, `fin_ms`, `valor` y `confianza` (entre 0 y 1). `UNIQUE (analisis_id, tipo, inicio_ms, fin_ms)`, para que reprocesar un segmento inserte con `INSERT OR IGNORE` y no duplique filas.
  - `fotogramas`: `tiempo_ms` y `ruta_relativa` a `data/`. `UNIQUE (analisis_id, tiempo_ms)`.
- `analisis.video_id` referencia a `videos` con `ON DELETE CASCADE`. `analisis.trabajo_id` referencia a `trabajos` con `ON DELETE SET NULL`.
- `jobs.service.confirmar_segmento` acepta un parámetro opcional `persistir`. Se ejecuta dentro de la misma transacción `BEGIN IMMEDIATE` que marca el segmento como `completado`. Si `persistir` falla, se deshacen las dos escrituras. `jobs` no conoce las tablas que escribe `persistir`.
- Las funciones de `analisis/repository.py` no hacen `commit`. Así no cierran la transacción de quien las llama.
- Un cambio de versión del analizador borra las señales y los fotogramas del análisis (D-015). Con la misma versión, un análisis fallido vuelve a `pendiente` y conserva sus resultados.
- Las miniaturas van en `work/<video_id>/fotogramas/<tiempo_ms>.jpg`. Se escriben en un `*.tmp` y se renombran con `os.replace`. Limitan su tamaño a 2 MiB y deben empezar con la cabecera JPEG.
- El barrido de miniaturas sin fila se hace dentro de una transacción `BEGIN IMMEDIATE`. Así un trabajo nuevo no puede empezar a escribir mientras se compara con la base. Si hay un trabajo ejecutándose, el barrido no corre.
- No hay endpoint de creación. `preparar_analisis` solo lo llama código del servidor.
- El vocabulario de tipos de señal se valida por formato (minúsculas, números y guion bajo, hasta 32 caracteres), no por lista cerrada. La lista concreta se fijará al implementar audio y visión. Agregar tipos no exige migración.

**Alternativas descartadas.**

- Que `analisis` escriba en `segmentos_trabajo` o que `jobs` escriba en `senales`. Rompe D-012.
- Confirmar el segmento primero y escribir las señales después, en otra transacción. Un fallo entre las dos dejaría un segmento completado sin datos.

**Consecuencias.** Un analizador nunca escribe en la base directamente. Devuelve su resultado al proceso del trabajo, y ese proceso lo pasa a `persistir`. Un cambio en `confirmar_segmento` que separe las dos escrituras rompe esta garantía.

---

## D-045. Contrato de analizadores, registro y API de consulta
**Fecha:** Módulo 2, Etapa 2
**Estado:** Aprobada por el usuario al autorizar la Etapa 2.

**Decisión.**

- `app/plugins/contrato.py` define `Senal`, `FotogramaProducido`, `SegmentoEntrada` y `ResultadoSegmento`, todos inmutables y validados al crearse. También define los protocolos `AlmacenFotogramas` y `Analizador`. Un analizador tiene `id`, `version` y `analizar_segmento(segmento, almacen)`. No recibe acceso a la base de datos.
- `app/plugins/registro.py` tiene el registro de analizadores. Valida el identificador, la versión y la duplicidad. Está vacío hasta la Etapa 3. Los módulos `audio` y `vision` no existen todavía, para no crear archivos vacíos (D-016).
- La API es de solo lectura, bajo `/api/v1/videos/{id}/analisis`:
  - `GET ""`: lista los análisis del video.
  - `GET /{analizador}`: devuelve un análisis.
  - `GET /{analizador}/senales?inicio_ms&fin_ms&limite`: devuelve las señales que se solapan con el intervalo. Límite de 1 a 2000, 500 por defecto.
  - `GET /{analizador}/fotogramas?limite`: devuelve los tiempos de los fotogramas.
  - `GET /{analizador}/fotogramas/{tiempo_ms}/miniatura`: devuelve el JPEG con `Cache-Control: no-store`.
- Las respuestas no incluyen rutas del sistema. La miniatura se sirve leyendo bloques, no cargando el archivo completo.
- Antes de servir una miniatura se comprueba que la ruta registrada coincide con la del almacén y que el archivo queda dentro de `data/`, aunque haya enlaces o junctions.
- Proxy (amplía D-036): entradas nuevas para cada endpoint. Los parámetros `inicio_ms` y `fin_ms` aceptan cero. El destino de miniaturas declara `image/jpeg`, y el proxy responde 502 si el backend devuelve otro tipo con éxito. No se agregó el parámetro `tipo` de D-036, porque la API todavía no lo necesita.

**Consecuencias.** Los analizadores de la Etapa 3 se registran en el registro y escriben sus resultados a través de `confirmar_segmento`. Hasta entonces, la API devuelve listas vacías o 404. No hay datos simulados.

---

## D-046. Eliminación de datos derivados de un video
**Fecha:** Módulo 2, Etapa 3. Pendiente A de la Etapa 2.
**Estado:** Aprobada por el usuario al autorizar la Etapa 3.

**Decisión.**

- `videos.service.eliminar` abre una transacción. Dentro, pide a `analisis.service.preparar_eliminacion` que compruebe que ningún análisis del video tiene un trabajo activo y que borre sus análisis. Las señales y los fotogramas se borran en cascada. Después borra la fila del video.
- Si un análisis del video tiene un trabajo en cola o ejecutándose, la eliminación responde 409 y no borra nada.
- Después del `COMMIT`, `analisis.service.borrar_archivos_derivados` borra las miniaturas (`.jpg`) y temporales (`.tmp`) de `work/<video_id>/fotogramas`. Luego quita los directorios que quedan vacíos.
- Un fallo al borrar una miniatura no cambia la respuesta (204). Se registra en el log y el archivo queda huérfano.
- Al arrancar, `analisis.service.limpiar_derivados_huerfanos` borra las miniaturas de los directorios `work/<número>` cuyo id ya no existe en `videos`. Es la recuperación de huérfanos. Un fallo en esa limpieza se registra y no impide arrancar.
- Ninguna de estas operaciones sigue enlaces simbólicos ni junctions en la ruta. Tampoco toca archivos fuera de `data/`, ni el original del video.
- El video no accede a las tablas de análisis: llama a `analisis.service`. `analisis` no accede a la tabla `videos`: usa `videos.service.ids_existentes`.
- Los ids de `videos` son `AUTOINCREMENT`, así que un id eliminado no se reutiliza y una miniatura huérfana no puede asignarse a un video nuevo.

**Alternativas descartadas.**

- Borrar los archivos antes de la transacción. Un fallo de la base dejaría miniaturas borradas que la base sigue referenciando.
- Dejar la limpieza sin barrido de arranque. Un fallo de borrado dejaría archivos sin forma de recuperarlos.

**Consecuencias.** Un análisis en curso bloquea la eliminación de su video hasta que termine o se cancele. Un análisis con trabajo ya terminado no bloquea.

---

## D-047. Rutas absolutas fuera de la API de videos
**Fecha:** Módulo 2, Etapa 3. Pendiente B de la Etapa 2.
**Estado:** Aprobada por el usuario al autorizar la Etapa 3.

**Decisión.**

- `VideoRespuesta` ya no tiene `ruta`. Tiene `nombre_archivo`, el nombre del archivo original. La reproducción sigue por `GET /videos/{id}/stream`.
- `POST /videos/seleccion` ya no devuelve la ruta elegida. Devuelve `{seleccion_id, nombre_archivo}`. La ruta queda en `RegistroSelecciones` (`modules/videos/selecciones.py`), en memoria del backend. La selección caduca a los 10 minutos, se usa una sola vez y el registro guarda como máximo 16 entradas.
- `POST /videos` acepta `ruta` (escrita por el usuario) o `seleccion_id`. Exactamente uno de los dos.
- Consumidores revisados: `DetalleVideo.tsx` muestra `nombre_archivo`. `ImportarVideo.tsx` envía `seleccion_id` en lugar de la ruta devuelta por el selector. `lib/api/videos.ts` y `lib/api/tipos.ts` se actualizaron. El proxy no necesita cambios porque reenvía el cuerpo JSON sin validar campos.
- La ruta absoluta solo existe en memoria del backend, en la base de datos (`ruta_original`) y en los procesos internos (`ruta_para_analisis`).
- Las pruebas `test_videos_privacidad.py` comprueban que ninguna respuesta pública de videos, análisis, proyectos, selección ni errores contiene la ruta del original ni la carpeta de datos.

**Consecuencias.** El campo `nombre` de `VideoRespuesta` se conserva, porque la interfaz ya lo usa como título. Hoy su valor coincide con `nombre_archivo`. Un cambio futuro que los separe debe documentarse aquí.

---

## D-048. Analizador de audio y vocabulario de señales v1.0.0
**Fecha:** Módulo 2, Etapa 3. Pendiente C y D de la Etapa 2.
**Estado:** Implementada. Parcialmente reemplazada por D-051 (umbral y duración mínima) y D-052 (vocabulario cerrado, que cierra la propuesta de esta decisión).

**Vocabulario (identificadores estables).**

- `energia_audio`: nivel medio de cada ventana de 200 ms. Valor normalizado de 0 a 1, donde 0 equivale a -90 dBFS o menos y 1 a 0 dBFS. Confianza 1.
- `silencio`: intervalo continuo de al menos 400 ms con nivel bajo el umbral adaptativo del video. Valor = (umbral - nivel medio en dB) / 20, acotado entre 0 y 1. Confianza 1.
- `cambio_intensidad`: par de ventanas consecutivas cuyo nivel cambia al menos 12 dB. El intervalo abarca las dos ventanas (400 ms). Valor = |cambio en dB| / 24, acotado entre 0 y 1. Confianza 1.

Todos los tiempos son enteros en milisegundos.

**Procesamiento.**

- FFmpeg entrega PCM s16le, mono, 16 kHz, por una tubería (D-030). Python lee ventana a ventana. No se escribe WAV.
- Un trabajo `analisis_audio` tiene segmentos `energia` de 60 s y un segmento final `consolidacion`. Cada segmento de energía se confirma con `jobs.service.confirmar_segmento`, en la misma transacción que sus señales.
- El segmento `consolidacion` calcula silencios y cambios sobre la serie completa. Escribe sus señales y marca el análisis como `completado` en la misma transacción.
- Si el trabajo falla, se cancela o pierde su reclamo, el análisis pasa a `fallido` con un mensaje corto. La cancelación se revisa entre ventanas.
- Si un trabajo cancelado en cola o terminado sin completar deja el análisis en `en_curso`, la API muestra `fallido`. La base se corrige al iniciar un análisis nuevo.

**Propuesta de umbral adaptativo (requiere confirmación).** No encontré en `docs/` ninguna regla de umbral aprobada. Usé esta regla: percentil 10 de los niveles del video, más 10 dB, acotado entre -55 y -35 dB. Si el usuario tiene la regla aprobada, se reemplaza en `senales.umbral_adaptativo`. No afecta al resto del código.

**Propuesta de contrato común (requiere aprobación antes de implementarse).** Hoy `Senal.tipo` se valida por formato (D-044). Para aplicar una lista cerrada harían falta tres cambios:

1. Una lista cerrada en `app/plugins/contrato.py`, que sea la fuente de verdad para `Senal`.
2. Un parámetro `tipo` en `lib/proxy/destinos.ts` con esa misma lista. Hoy existe el mismo acuerdo en D-036 pero no está implementado. Mantener dos listas (Python y TypeScript) exige una prueba de paridad.
3. Un filtro `tipo` en `GET /videos/{id}/analisis/{analizador}/senales`.

Mientras no se apruebe, el vocabulario de audio queda documentado aquí y en `senales.py`, y la API no filtra por tipo.

**Consecuencias.** Un analizador nuevo debe declarar sus tipos con la misma regla de formato. Un cambio de definición de un tipo existente exige una versión nueva del analizador, para que sus resultados previos se invaliden (D-015).

---

## D-049. Composición de analizadores y tipos de trabajo
**Fecha:** Módulo 2, Etapa 3.
**Estado:** Aprobada por el usuario al autorizar la Etapa 3.

**Decisión.**

- `app/composicion.py` es el único lugar donde se registran los analizadores (`REGISTRO`) y los tipos de trabajo que necesitan módulos de análisis (`jobs.tareas.registrar`).
- Lo llaman `crear_aplicacion` y el proceso hijo de cada trabajo (`app.jobs.ejecutar`). Ambos necesitan el mismo registro.
- `jobs` no importa módulos de análisis. Así no hay importaciones circulares.
- `jobs.service.crear` acepta `al_insertar`. Ese callback se ejecuta dentro de la misma transacción que crea el trabajo. `audio` lo usa para dejar el análisis en curso sin que quede un trabajo sin reservar, o un análisis reservado sin trabajo.

**Consecuencias.** Un módulo nuevo de análisis se registra en `composicion.registrar`, no en `jobs`.

---

## D-050. Prueba intermitente `test_cancelacion_mata_al_proceso_nieto`
**Fecha:** Módulo 2, Etapa 3. Pendiente E de la Etapa 2.
**Estado:** Aprobada por el usuario al autorizar la Etapa 3.

**Hallazgo.** No reproduje el fallo. Ejecuté la prueba 25 veces en serie, 20 veces con ocho procesos de carga de CPU, 24 veces en cuatro ejecuciones paralelas, y la carpeta de pruebas de trabajos seis veces seguidas. Todas pasaron.

**Causa probable.** El protocolo de publicación del PID del nieto no era atómico. El nieto creaba `nieto.pid` con `write_text` directo, así que el lector podía encontrar el archivo ya creado y todavía sin contenido. La prueba reintentaba solo mientras el contenido no fuera numérico, y no distinguía ese estado de un error de lectura. Un `PermissionError` transitorio (por ejemplo, un antivirus que bloquea el archivo recién creado) fallaba la prueba sin explicación.

**Corrección.**

- El nieto escribe `nieto.pid.tmp` y luego hace `os.replace` a `nieto.pid` (`jobs/tareas.py`). El lector ve el archivo final completo o no lo ve.
- La prueba espera el valor con `_esperar_valor`, que solo espera a que el archivo final exista y tenga un PID válido. Un `PermissionError` se propaga como fallo. No se reintenta.
- No se añadieron reintentos ni se subió el tiempo de espera.

**Limitación.** Si el fallo original fue otra causa, esta corrección no la elimina. Sin reproducción no hay confirmación. Si vuelve a aparecer, el mensaje de error de `_esperar_valor` y el log del worker indicarán en qué paso se detuvo.

**Consecuencias.** Cualquier proceso que publique un archivo que otro proceso lee debe escribir a un temporal y renombrar.

---

## D-051. Umbral adaptativo y duración mínima de silencio
**Fecha:** Módulo 2, Etapa 3. Revisión de la Etapa 3.
**Estado:** Aprobada por el usuario. Reemplaza los valores de D-048.

**Decisión.**

- Umbral del video: percentil 10 de los niveles de ventana, más 12 dB, acotado entre -55 y -35 dBFS. (D-048 usaba 10 dB.)
- Duración mínima de un silencio: 500 ms. (D-048 usaba 400 ms.) Con ventanas de 200 ms, el silencio más corto que se reporta ocupa tres ventanas.
- El resto de reglas de D-048 se mantiene: la consolidación usa la serie completa del video, y los tramos de silencio y de cambio nunca se unen a través de un hueco de tiempo.

**Consecuencias.** Un silencio de 400 ms deja de reportarse. Los resultados ya guardados con la versión 1.0.0 del analizador no cambian sin reanalizar. Un cambio de estos valores exige subir la versión del analizador para que los resultados previos se invaliden (D-015).

---

## D-052. Vocabulario cerrado de tipos de señal
**Fecha:** Módulo 2, Etapa 3. Revisión de la Etapa 3.
**Estado:** Aprobada por el usuario. Cierra la propuesta de contrato común de D-048. Reemplaza la validación de formato de D-044 para el campo `tipo`.

**Decisión.**

1. `app/plugins/contrato.py` define `TIPOS_SENAL_PERMITIDOS`. Es la única fuente de verdad. Hoy contiene `energia_audio`, `silencio` y `cambio_intensidad`. `Senal` rechaza cualquier otro tipo, además de la validación de formato.
2. `frontend/src/lib/proxy/destinos.ts` exporta `TIPOS_SENAL_PERMITIDOS` con la misma lista. El parámetro `tipo` de `GET /videos/{id}/analisis/{analizador}/senales` usa el validador `tipo_senal`. Un valor fuera de la lista responde 400 en el proxy.
3. `GET .../senales?tipo=` filtra por tipo. Un valor fuera de la lista responde 422 en el backend. El filtro es mayúsculas y minúsculas exactas.
4. La paridad se verifica con dos pruebas. La primera compara las dos listas por texto. La segunda ejecuta el validador real de `destinos.ts` con Node, si está instalado, y comprueba casos válidos e inválidos.
5. Los tipos visuales se agregarán cuando se implemente el módulo de visión. Agregar un tipo exige cambiar ambas listas, actualizar esta decisión y pasar la prueba de paridad.

**Consecuencias.** Las pruebas de persistencia usan solo tipos del vocabulario. Las filas que ya existen en la base no se validan de nuevo, porque la base conserva la regla de formato. Un tipo antiguo fuera de la lista sigue siendo legible, pero `Senal` no lo puede crear.

---

## D-053. Inicio de análisis por API
**Fecha:** Módulo 2, Etapa 3. Revisión de la Etapa 3.
**Estado:** Aprobada por el usuario.

**Decisión.** `POST /api/v1/videos/{id}/analisis` inicia los analizadores registrados que tengan lanzador. Responde 202 con una lista de `{analizador, accion, trabajo_id, estado, detalle}`. Las acciones son:

- `iniciado`: se creó un trabajo nuevo en cola. Devuelve su id.
- `en_curso`: ya hay un trabajo activo para ese analizador. Devuelve ese trabajo, sin crear otro.
- `sin_cambios`: el análisis está completo con la versión vigente. No se repite.
- `rechazado`: el video no admite el analizador, por ejemplo por no tener audio. Devuelve el motivo.

Reglas:

- Un análisis fallido o cancelado se reintenta con un trabajo nuevo.
- Video inexistente: 404. Archivo original no disponible: 409. No se crea nada en ninguno de los dos casos.
- La creación del trabajo y el estado `en_curso` del análisis ocurren en una sola transacción (`al_insertar` de D-049). Si otra petición gana la carrera, el `Conflicto` se convierte en `en_curso` con el trabajo de la otra.
- El límite de un trabajo pesado a la vez lo aplica el worker. Los trabajos nuevos quedan en cola en orden de llegada.
- El analizador de audio se entrega desde `composicion.lanzadores()` y `app.state.lanzadores`. El router no importa módulos concretos de análisis.
- El proxy permite `POST` solo en `videos/{id}/analisis`. Otros métodos responden 405.

**Consecuencias.** La API no tiene interfaz. El endpoint solo inicia análisis: no los detiene ni los borra.

---

## D-054. Cancelación de un análisis en cola
**Fecha:** Módulo 2, Etapa 3. Revisión de la Etapa 3.
**Estado:** Aprobada. El estado `cancelado` se implementó en D-055. Se mantiene la descripción de la propuesta como referencia histórica.

**Corrección implementada.**

- Cada tipo de trabajo puede registrar un gancho de cancelación en cola (`tareas.registrar(..., al_cancelar_en_cola=...)`). `jobs.service.cancelar` lo ejecuta dentro de la misma transacción que la cancelación.
- El gancho de audio llama a `analisis.service.cerrar_por_cancelacion`. Pasa el análisis en curso de ese trabajo a `fallido`, con el error `Análisis cancelado antes de ejecutarse.`. El cambio queda persistido en la base.
- Si un trabajo se cancela mientras ejecuta, la tarea marca el análisis como fallido con `Análisis cancelado.`.
- La lectura del análisis sigue corrigiendo los casos que el gancho no alcanza, por ejemplo un trabajo eliminado por el worker tras la gracia de cancelación. La respuesta muestra `fallido` mientras el trabajo no esté activo.

**Propuesta de estado `cancelado` (no implementada).**

- Impacto: la tabla `analisis` tiene `CHECK (estado IN ('pendiente', 'en_curso', 'completado', 'fallido'))`. SQLite no permite cambiar un `CHECK` con `ALTER TABLE`. Hay que reconstruir la tabla: crear `analisis_nueva`, copiar las filas, borrar `analisis` y renombrar. Como `senales` y `fotogramas` referencian `analisis` con `ON DELETE CASCADE`, borrar la tabla vieja con las claves externas activas borraría sus señales. La migración debe ejecutarse con `PRAGMA foreign_keys = OFF`, fuera de la transacción de migración, y verificar `PRAGMA foreign_key_check` antes de confirmar.
- Riesgo: si la migración falla a medio camino, los datos de análisis se pierden. Antes de aplicarla se haría una copia verificable, como en las etapas anteriores.
- Alternativa sin migración: guardar `fallido` con un código de motivo en una columna nueva, `ADD COLUMN motivo TEXT`. No requiere reconstruir la tabla, pero deja el estado y el motivo separados.
- Recomendación: la reconstrucción con `cancelado` como estado propio, porque la API y el proxy podrían distinguirlo sin leer el texto del error.

**Consecuencias.** Hasta que se decida, un análisis cancelado aparece como `fallido`, con el error que indica la cancelación.

---

## D-055. Estado `cancelado` y migración 0005
**Fecha:** Módulo 2, Etapa 3. Cierre de la Etapa 3.
**Estado:** Aprobada por el usuario. Implementada.

**Decisión.**

- `analisis.estado` admite `cancelado`. La migración `0005_analisis_cancelado.sql` reconstruye la tabla con el nuevo `CHECK`. No se añadió una columna `motivo`.
- La reconstrucción sigue el procedimiento de 12 pasos de SQLite. Conserva las columnas, la restricción `UNIQUE (video_id, analizador)`, `ON DELETE CASCADE` hacia `videos`, `ON DELETE SET NULL` hacia `trabajos`, y el contador `AUTOINCREMENT`. `senales` y `fotogramas` siguen referenciando `analisis` con `ON DELETE CASCADE`.
- Las claves externas se desactivan antes de abrir la transacción. El runner de migraciones (`app/db/migraciones.py`) reconoce una migración que las necesita por su primera línea (`-- requiere: claves_externas_desactivadas`). Antes de confirmar ejecuta `PRAGMA foreign_key_check` y `PRAGMA integrity_check`. Si alguno falla, hace `ROLLBACK`. Al terminar, restaura el valor previo de `foreign_keys`, haya éxito o fallo.
- Las migraciones sin esa marca siguen usando el camino anterior, sin cambios.

**Estrategia de recuperación.** Antes de aplicar la migración en una base real se genera una copia con la API de backup de SQLite. Se verifica con `integrity_check`, con los conteos de cada tabla y con el SHA-256 del archivo. Si la migración falla, la transacción se deshace y la base queda en la versión 4. Un fallo a medio camino no deja la base parcialmente migrada.

**Estados y transiciones.**

| Desde | Evento | Hasta |
|---|---|---|
| (nuevo) | Inicio (`iniciar`, API o servidor) | `en_curso` |
| `en_curso` | Consolidación confirmada | `completado` |
| `en_curso` | Error de la tarea o del proceso | `fallido` (conserva resultados, D-044) |
| `en_curso` | Cancelación en cola, cancelación en ejecución o terminación forzada | `cancelado` (sin resultados, D-057) |
| `cancelado` o `fallido` | Inicio nuevo | `en_curso` |
| `completado` con versión vigente | Inicio nuevo | Sin cambios (`sin_cambios`) |

**Consecuencias.** La API y el proxy transportan el estado como texto. El proxy no valida estados, así que no requirió cambios. El frontend no muestra estados de análisis.

---

## D-056. Cierre de trabajos y gancho de terminación
**Fecha:** Módulo 2, Etapa 3. Cierre de la Etapa 3.
**Estado:** Aprobada por el usuario. Implementada.

**Decisión.**

- Todo cierre de un trabajo sin éxito llama al gancho de su tipo (`tareas.registrar(..., al_terminar=...)`), dentro de la misma transacción. El gancho recibe `(conexión, trabajo_id, estado, error)`, donde `estado` es `cancelado` o `fallido`.
- Los cierres cubiertos son: cancelación en cola, cancelación pedida al proceso, cierre tras la salida del proceso, reencolado sin intentos restantes, y fallo registrado por el proceso del trabajo.
- Así el análisis se cierra aunque lo cierre el supervisor. No depende del proceso hijo.
- El supervisor clasifica la terminación con un motivo explícito (`salida`, `parada` o `cancelacion_forzada`). Solo estos motivos pueden producir `cancelado`:
  - `cancelacion_forzada`: el supervisor terminó el proceso tras la gracia de cancelación. Es cancelación si hay cancelación pedida.
  - `parada`: parada ordenada del worker. Es cancelación si hay cancelación pedida. Si no la hay, reencola sin contar como fallo.
  - `salida`: el proceso terminó solo. Sin resultado confirmado es `fallido`, aunque hubiera cancelación pedida. Un error real nunca se registra como cancelación.
- Un motivo desconocido lanza `ValueError`.

**Consecuencias.** Un tipo nuevo de trabajo que deba cerrar un resultado propio registra su gancho. `jobs` no importa a los módulos de análisis.

---

## D-057. Política de señales en cancelaciones y fallos
**Fecha:** Módulo 2, Etapa 3. Cierre de la Etapa 3.
**Estado:** Aprobada por el usuario. Implementada.

**Decisión.**

1. **Cancelado: no se conservan señales.** Al pasar a `cancelado`, se borran en la misma transacción las señales y los fotogramas del análisis (`borrar_resultados`). Un reintento recalcula los segmentos desde cero. Así no queda ninguna señal parcial que la API pueda presentar como resultado.
2. **Fallido: se conservan los segmentos confirmados** (D-044). Son válidos para la misma versión del analizador, porque cada segmento es determinista. El reintento reutiliza esas filas por `INSERT OR IGNORE`. Un fallo no implica que las señales sean inválidas.
3. **Miniaturas.** Para análisis con fotogramas, al cancelar se borran sus filas. Los archivos `.jpg` quedan en disco hasta el siguiente barrido de huérfanos (D-032). El análisis de audio no genera miniaturas.
4. **Registros huérfanos.** Las señales siempre referencian un análisis existente (`ON DELETE CASCADE`), y `foreign_key_check` lo comprueba. La prueba con worker real verifica que no quedan señales sin análisis ni referencias rotas.
5. **Consolidación.** Los silencios y cambios se escriben junto con el estado `completado`, en la misma transacción. Un análisis cancelado antes de la consolidación no tiene silencios parciales.

**Consecuencias.** Cancelar un análisis largo y reintentarlo repite el cálculo de los segmentos ya confirmados. Es el costo de no conservar resultados parciales. Si ese costo resulta alto, se puede cambiar a conservación con reemplazo seguro en una decisión posterior.
