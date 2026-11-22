from typing import Annotated

from pydantic import BaseModel, StringConstraints

NombreProyecto = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)
]


class ProyectoCrear(BaseModel):
    nombre: NombreProyecto


class ProyectoRespuesta(BaseModel):
    id: int
    nombre: str
    creado: str
    cantidad_videos: int
