from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

RAIZ_REPOSITORIO = Path(__file__).resolve().parents[3]

ORIGENES_PERMITIDOS = frozenset({"http://localhost:3000", "http://127.0.0.1:3000"})
HOSTS_PERMITIDOS = frozenset({"127.0.0.1:8000", "localhost:8000"})


class Configuracion(BaseSettings):
    """Configuración leída de variables de entorno con prefijo CLIPPERAI_."""

    model_config = SettingsConfigDict(env_prefix="CLIPPERAI_", extra="ignore")

    data_dir: Path = RAIZ_REPOSITORIO / "data"
    ffmpeg: Path | None = None
    ffprobe: Path | None = None
    iniciar_trabajos: bool = True

    @property
    def ruta_base_datos(self) -> Path:
        return self.data_dir / "clipperai.db"

    @property
    def ruta_token(self) -> Path:
        return self.data_dir / "runtime" / "sesion.token"

    @property
    def ruta_bloqueo_worker(self) -> Path:
        return self.data_dir / "runtime" / "worker.lock"


def cargar_configuracion() -> Configuracion:
    return Configuracion()
