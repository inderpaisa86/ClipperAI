from pydantic import BaseModel, Field, model_validator


class VideoCrear(BaseModel):
    """Origen del video: una ruta escrita por el usuario o una selección del selector nativo. Exactamente uno."""

    proyecto_id: int = Field(gt=0)
    ruta: str | None = Field(default=None, min_length=1, max_length=4096)
    seleccion_id: str | None = Field(default=None, min_length=1, max_length=64)

    @model_validator(mode="after")
    def exigir_un_origen(self) -> "VideoCrear":
        if (self.ruta is None) == (self.seleccion_id is None):
            raise ValueError("Indique una ruta o una selección, no ambas.")
        return self


class VideoRespuesta(BaseModel):
    """Metadatos públicos del video. La ruta absoluta del original nunca sale del backend."""

    id: int
    proyecto_id: int
    nombre: str
    nombre_archivo: str
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
    """Resultado del selector. Ambos campos son null si el usuario cancela."""

    seleccion_id: str | None
    nombre_archivo: str | None
