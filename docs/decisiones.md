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

**Consecuencias.** Un enlace simbólico en la última posición de la ruta se rechaza. Un enlace en un directorio intermedio no se detecta. Ese caso queda documentado como límite.

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
