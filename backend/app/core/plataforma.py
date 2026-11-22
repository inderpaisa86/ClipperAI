import os
import platform
from dataclasses import dataclass

_SISTEMAS = {"Windows": "windows", "Darwin": "macos", "Linux": "linux"}
_ARQUITECTURAS = {
    "amd64": "x86_64",
    "x86_64": "x86_64",
    "arm64": "arm64",
    "aarch64": "arm64",
}


@dataclass(frozen=True)
class InfoPlataforma:
    sistema: str
    arquitectura: str
    cpus_logicas: int

    @property
    def es_apple_silicon(self) -> bool:
        return self.sistema == "macos" and self.arquitectura == "arm64"


def detectar_plataforma() -> InfoPlataforma:
    sistema = _SISTEMAS.get(platform.system(), "desconocido")
    maquina = platform.machine().lower()
    arquitectura = _ARQUITECTURAS.get(maquina, maquina or "desconocida")
    return InfoPlataforma(
        sistema=sistema,
        arquitectura=arquitectura,
        cpus_logicas=os.cpu_count() or 1,
    )
