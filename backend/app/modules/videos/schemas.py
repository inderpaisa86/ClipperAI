from pydantic import BaseModel, Field


class VideoCrear(BaseModel):
    proyecto_id: int = Field(gt=0)
    ruta: str = Field(min_length=1, max_length=4096)


class VideoRespuesta(BaseModel):
    id: int
    proyecto_id: int
    nombre: str
    ruta: str
    tamano_bytes: int
    duracion_segundos: float | None
    ancho: int
    alto: int
    fps: float | None
    codec_video: str
    codec_audio: str | None
    formato: str
    disponible: bool
    creado: str


class SeleccionRespuesta(BaseModel):
    ruta: str | None
