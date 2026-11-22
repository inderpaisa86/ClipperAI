from pydantic import BaseModel


class TrabajoRespuesta(BaseModel):
    id: int
    tipo: str
    estado: str
    progreso: int
    cancelacion_solicitada: bool
    intentos: int
    error: str | None
    creado: str
    actualizado: str
