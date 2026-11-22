from pathlib import Path


class RutaNoPermitida(ValueError):
    pass


class RaizDatos:
    """Directorio raíz de datos. Toda ruta relativa se resuelve dentro de él."""

    def __init__(self, raiz: Path) -> None:
        self.raiz = raiz.expanduser().resolve()

    def resolver(self, relativa: str | Path) -> Path:
        candidata = Path(relativa)
        if candidata.is_absolute() or candidata.anchor or ".." in candidata.parts:
            raise RutaNoPermitida(f"La ruta debe ser relativa a la raíz de datos: {relativa}")

        resuelta = (self.raiz / candidata).resolve()
        if not resuelta.is_relative_to(self.raiz):
            raise RutaNoPermitida(f"La ruta sale de la raíz de datos: {relativa}")
        return resuelta
