from pathlib import Path


def crear_proyecto(cliente, nombre: str = "Proyecto de prueba") -> int:
    respuesta = cliente.post("/api/v1/proyectos", json={"nombre": nombre})
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()["id"]


def importar_video(cliente, proyecto_id: int, ruta: Path | str):
    return cliente.post("/api/v1/videos", json={"proyecto_id": proyecto_id, "ruta": str(ruta)})


def persistir_en_transaccion(conexion, raiz, analisis_id: int, resultado) -> None:
    """Persiste un resultado dentro de una transacción, como lo hace jobs.confirmar_segmento en producción."""
    from app.db.conexion import transaccion_inmediata
    from app.modules.analisis import service

    with transaccion_inmediata(conexion):
        service.persistir_resultado(conexion, raiz, analisis_id, resultado)


class AnalizadorFalso:
    """Analizador de prueba que cumple el contrato. No procesa video."""

    def __init__(self, identificador: str = "audio", version: str = "1") -> None:
        self._identificador = identificador
        self._version = version

    @property
    def id(self) -> str:
        return self._identificador

    @property
    def version(self) -> str:
        return self._version

    def analizar_segmento(self, segmento, almacen):
        from app.plugins.contrato import ResultadoSegmento

        return ResultadoSegmento()


def registro_con(*analizadores: AnalizadorFalso):
    from app.plugins.registro import RegistroAnalizadores

    registro = RegistroAnalizadores()
    for analizador in analizadores:
        registro.registrar(analizador)
    return registro


JPEG_PRUEBA = b"\xff\xd8\xff\xe0" + b"0" * 128


def insertar_video_directo(conexion, proyecto_id: int, nombre: str = "video.mp4") -> int:
    """Registra un video sin FFprobe. Sirve para probar análisis sin depender de FFmpeg."""
    cursor = conexion.execute(
        "INSERT INTO videos (proyecto_id, nombre, ruta_original, tamano_bytes, ancho, alto, codec_video, formato) "
        "VALUES (?, ?, ?, 1024, 1280, 720, 'h264', 'mp4')",
        (proyecto_id, nombre, f"/medios/{proyecto_id}/{nombre}"),
    )
    conexion.commit()
    return int(cursor.lastrowid)
