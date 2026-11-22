from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.configuracion import (
    HOSTS_PERMITIDOS,
    ORIGENES_PERMITIDOS,
    Configuracion,
    cargar_configuracion,
)
from app.core.errores import ErrorAplicacion
from app.core.seguridad import escribir_token, generar_token, token_valido
from app.db.conexion import conectar
from app.db.migraciones import aplicar_migraciones
from app.modules.projects.router import router as router_proyectos
from app.modules.sistema.router import router as router_sistema
from app.modules.videos.router import router as router_videos

ENCABEZADO_TOKEN = "X-ClipperAI-Token"
PREFIJO_API = "/api/v1"


def crear_aplicacion(configuracion: Configuracion | None = None) -> FastAPI:
    config = configuracion or cargar_configuracion()

    @asynccontextmanager
    async def ciclo_de_vida(app: FastAPI) -> AsyncIterator[None]:
        config.data_dir.mkdir(parents=True, exist_ok=True)
        conexion = conectar(config.ruta_base_datos)
        try:
            aplicar_migraciones(conexion)
        finally:
            conexion.close()

        token = generar_token()
        escribir_token(config.ruta_token, token)
        app.state.configuracion = config
        app.state.token = token
        try:
            yield
        finally:
            config.ruta_token.unlink(missing_ok=True)

    app = FastAPI(title="ClipperAI", version="0.1.0", lifespan=ciclo_de_vida)

    @app.exception_handler(ErrorAplicacion)
    async def manejar_error_aplicacion(request: Request, error: ErrorAplicacion) -> JSONResponse:
        return JSONResponse({"detalle": error.mensaje}, status_code=error.estado)

    @app.exception_handler(RequestValidationError)
    async def manejar_datos_invalidos(
        request: Request, error: RequestValidationError
    ) -> JSONResponse:
        primero = error.errors()[0] if error.errors() else {}
        campo = ".".join(str(parte) for parte in primero.get("loc", [])[1:]) or "datos"
        return JSONResponse(
            {"detalle": f"Dato no válido en '{campo}'."},
            status_code=422,
        )

    @app.middleware("http")
    async def proteger_acceso(
        request: Request, siguiente: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.headers.get("host", "") not in HOSTS_PERMITIDOS:
            return JSONResponse({"detalle": "Host no permitido"}, status_code=403)

        origen = request.headers.get("origin")
        if origen is not None and origen not in ORIGENES_PERMITIDOS:
            return JSONResponse({"detalle": "Origen no permitido"}, status_code=403)

        if request.url.path.startswith(PREFIJO_API):
            recibido = request.headers.get(ENCABEZADO_TOKEN)
            if not token_valido(recibido, request.app.state.token):
                return JSONResponse({"detalle": "Token de sesión inválido"}, status_code=401)

        return await siguiente(request)

    app.include_router(router_sistema, prefix=PREFIJO_API)
    app.include_router(router_proyectos, prefix=PREFIJO_API)
    app.include_router(router_videos, prefix=PREFIJO_API)
    return app


app = crear_aplicacion()
