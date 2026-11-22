# Instrucciones para agentes de IA

Este archivo lo leen los agentes que trabajan en ClipperAI. Antes de cambiar código, lee `docs/arquitectura.md` y `docs/decisiones.md`.

## Qué es el proyecto

ClipperAI es una aplicación local que analiza videos y propone clips. El desarrollo inicial es en Windows. El destino incluye macOS Intel y Apple Silicon (D-017). Todo el procesamiento ocurre en el equipo del usuario. Ningún video se sube a servicios externos.

## Decisiones fijas

Estas decisiones están aprobadas. No las cambies sin confirmación del usuario. Si propones un cambio, regístralo como una decisión nueva en `docs/decisiones.md`.

- Frontend: Next.js. Backend: Python 3.12 con FastAPI.
- Multimedia: FFmpeg y FFprobe. Visión: OpenCV. Transcripción: faster-whisper con modelo `small`, CPU, INT8.
- Base de datos: SQLite. Cola de trabajos: tabla SQLite con worker propio. No usar Celery ni Redis.
- Gestor Python: uv con `uv.lock`. Gestor Node: npm.
- Importación por referencia por defecto. Copia opcional a `data/media/`. No usar multipart para videos.
- Polling de progreso cada 2 segundos.
- Organización del backend por dominio en `backend/app/modules/`.
- Perfiles como archivos JSON en `backend/app/perfiles/`. No se añaden perfiles codificados en el motor.

## Reglas de trabajo

- **No reinstalar herramientas ya instaladas:** Python 3.12, Node.js 24.19.0, npm 11.17.0, Git 2.55.0 y FFmpeg/FFprobe 9.1.
- **No instalar dependencias sin autorización.** Esto incluye paquetes de npm, paquetes de pip, uv y cualquier herramienta del sistema.
- **No hacer commits.** Los commits los hace el usuario. Antes de cualquier operación de Git que cree un commit, pide confirmación.
- **No procesar videos con servicios externos.** No envíes contenido de video, audio ni transcripciones a APIs de terceros.
- **No crear archivos vacíos.** Crea un archivo solo cuando tenga contenido real. Un módulo incluye `router.py`, `service.py`, `repository.py` o `schemas.py` solo si los necesita.
- **Un módulo no accede a las tablas de otro.** Usa el servicio del otro módulo.
- **No escribir lógica de un juego o de un perfil en el motor.** Eso va en perfiles (JSON) o en analizadores (`plugins/`).
- **Rutas de archivos.** Las rutas dentro del directorio de datos pasan por `core/rutas.py`. Las rutas de videos que elige el usuario se validan con `validar_ruta_entrada` en `modules/videos/service.py` (D-024). Nunca confíes en una ruta que venga del cliente sin validarla.
- **Videos originales.** Nunca modifiques, copies ni borres un archivo original desde el código de ClipperAI. Eliminar un video borra solo su registro.
- **Transmisión.** Lee los videos en bloques (`iterar_archivo`). Nunca cargues un video completo en memoria.
- **Subprocesos.** FFmpeg y FFprobe se lanzan con lista de argumentos. Nunca con cadena de shell.
- **Seguridad de la API.** Todo endpoint `/api/v1` valida `Origin`, `Host` y el token de sesión. No desactives esas validaciones para facilitar pruebas.
- **Secretos.** El token de sesión vive en `data/runtime/`. No lo escribas en código, en logs ni en documentación.
- **Escritura de salidas.** Escribe en un `*.tmp` y renombra con `os.replace`. Marca el estado como completado solo después.
- **Multiplataforma (D-017).**
  - Usa `pathlib` para todas las rutas. No escribas rutas absolutas, letras de unidad ni rutas como `C:\Users\...` en el código ni en la configuración.
  - No escribas ramas de código por sistema operativo fuera de `core/plataforma.py`, `core/herramientas.py` y `core/dialogo_archivos.py`.
  - No introduzcas dependencias exclusivas de Windows, de macOS o de NVIDIA/CUDA sin registrar una decisión.
  - No resuelvas FFmpeg o FFprobe con rutas fijas. Usa `core/herramientas.py`.
  - Los scripts de arranque solo inician servicios. Hay uno para Windows (`.ps1`) y otro para macOS (`.sh`).
  - Las pruebas usan directorios temporales y no dependen de rutas del equipo.
- **Frontend y proxy (D-020, D-021).**
  - Nunca uses `NEXT_PUBLIC_` para tokens, rutas del sistema ni configuración del backend.
  - El navegador nunca llama directamente al backend. Usa `lib/api/cliente.ts`, que llama al proxy `/api/backend/*`.
  - Un endpoint nuevo del backend se expone solo agregándolo a la lista blanca de `lib/proxy/destinos.ts` y registrando una decisión.
  - No agregues librerías de interfaz, gráficos o edición de video sin justificarlas y pedir aprobación.
  - Los componentes de cliente (`"use client"`) no importan `lib/servidor/*`.
- **macOS no se instala ni se prueba** hasta que el usuario lo pida. Solo se verifica que las decisiones no lo bloqueen.

## Idioma

- Documentación y mensajes al usuario: español.
- Identificadores de código: español, con los nombres técnicos estándar cuando existan (por ejemplo `router`, `schema`, `repository`).

## Dónde está cada cosa

| Tema | Ubicación |
|---|---|
| Arquitectura y estructura | `docs/arquitectura.md` |
| Decisiones y su historial | `docs/decisiones.md` |
| Contrato de la API | `docs/api.md` (se genera desde OpenAPI) |
| Datos locales | `data/` (fuera de Git) |

## Antes de terminar una tarea

1. Ejecuta las pruebas del módulo que modificaste.
2. Confirma que no quedan archivos temporales ni archivos vacíos nuevos.
3. Resume al usuario qué cambió y qué no pudiste verificar.
