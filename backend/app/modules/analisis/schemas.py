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


class FotogramaRespuesta(BaseModel):
    """Solo el tiempo. La imagen se pide a su propio endpoint y la ruta en disco nunca sale de la API."""

    tiempo_ms: int
