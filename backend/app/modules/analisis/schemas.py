from pydantic import BaseModel


class AnalisisRespuesta(BaseModel):
    id: int
    video_id: int
    analizador: str
    version_analizador: str
    estado: str
    error: str | None
    creado: str
    actualizado: str


class SenalRespuesta(BaseModel):
    tipo: str
    inicio_ms: int
    fin_ms: int
    valor: float
    confianza: float


class InicioAnalisisRespuesta(BaseModel):
    """Resultado de iniciar un analizador para un video.

    accion: `iniciado` (trabajo nuevo), `en_curso` (ya había un trabajo activo y se devuelve ese),
    `sin_cambios` (análisis completo con la versión vigente) o `rechazado` (el video no admite este analizador).
    """

    analizador: str
    accion: str
    trabajo_id: int | None
    estado: str | None
    detalle: str | None


class FotogramaRespuesta(BaseModel):
    """Solo el tiempo. La imagen se pide a su propio endpoint y la ruta en disco nunca sale de la API."""

    tiempo_ms: int
