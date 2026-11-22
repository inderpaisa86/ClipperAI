# ClipperAI

Aplicación local para analizar videos y proponer clips listos para edición y publicación. Sirve para gaming, podcasts, humor, educación, entrevistas y otros contenidos.

Todo el procesamiento ocurre en tu equipo. Ningún video se sube a servicios externos.

**Estado:** Fase 1 en curso. Hay backend, frontend y gestión inicial de videos (registro, metadatos, previsualización y eliminación de registros). El análisis todavía no está implementado.

**Datos de desarrollo:** los proyectos y videos registrados en `data/clipperai.db` son de pruebas. No se deben borrar ni recrear la base sin decidirlo antes.

## Requisitos

- Windows 11 de 64 bits.
- Python 3.12.
- Node.js 24 y npm.
- FFmpeg y FFprobe 9.1 en el PATH.
- uv, para gestionar las dependencias de Python.

Un equipo con 16 GB de RAM y CPU Intel de 4 núcleos es suficiente. No se requiere GPU NVIDIA.

## Documentación

- [Arquitectura](docs/arquitectura.md): estructura, flujo de procesamiento, seguridad y recuperación.
- [Decisiones](docs/decisiones.md): registro de decisiones técnicas y su motivo.
- [Instrucciones para agentes](AGENTS.md): reglas para herramientas que modifican el proyecto.

## Ejecución del backend

Desde la raíz del repositorio:

```powershell
# Windows
.\scripts\arrancar_windows.ps1
```

```bash
# macOS (pendiente de prueba)
bash scripts/arrancar_macos.sh
```

El backend escucha en `http://127.0.0.1:8000`. Genera un token de sesión en `data/runtime/sesion.token` al arrancar. Cada petición a `/api/v1` debe enviar ese token en la cabecera `X-ClipperAI-Token`.

Para ejecutar las pruebas:

```powershell
cd backend
uv run pytest
```

### Frontend

```powershell
cd frontend
npm install
npm run dev
```

La interfaz queda disponible en `http://127.0.0.1:3000` (o `http://localhost:3000`). Para producción: `npm run build` seguido de `npm run start`.

El navegador no recibe el token del backend. Las peticiones pasan por `/api/backend/*`, que valida el origen y reenvía al backend con el token.

Comandos de comprobación del frontend:

```powershell
npm run lint
npm run typecheck
```
