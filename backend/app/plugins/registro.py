"""Registro de analizadores disponibles.

Audio y visión se registrarán en etapas posteriores. Hasta entonces el registro está vacío y
ninguna consulta ni trabajo puede producir análisis.
"""

from app.plugins.contrato import (
    LONGITUD_VERSION_MAXIMA,
    PATRON_IDENTIFICADOR,
    Analizador,
    ContratoInvalido,
)


class AnalizadorNoRegistrado(LookupError):
    """No hay ningún analizador con ese identificador."""


class RegistroAnalizadores:
    def __init__(self) -> None:
        self._analizadores: dict[str, Analizador] = {}

    def registrar(self, analizador: Analizador) -> None:
        if not isinstance(analizador, Analizador):
            raise ContratoInvalido("El objeto no cumple el contrato de analizador.")
        identificador = analizador.id
        if not isinstance(identificador, str) or not PATRON_IDENTIFICADOR.fullmatch(identificador):
            raise ContratoInvalido("El identificador del analizador no es válido.")
        version = analizador.version
        if not isinstance(version, str) or not 0 < len(version) <= LONGITUD_VERSION_MAXIMA:
            raise ContratoInvalido("La versión del analizador no es válida.")
        if identificador in self._analizadores:
            raise ContratoInvalido("Ya existe un analizador con ese identificador.")
        self._analizadores[identificador] = analizador

    def obtener(self, identificador: str) -> Analizador:
        analizador = self._analizadores.get(identificador)
        if analizador is None:
            raise AnalizadorNoRegistrado(identificador)
        return analizador

    def existe(self, identificador: str) -> bool:
        return identificador in self._analizadores

    def identificadores(self) -> tuple[str, ...]:
        return tuple(sorted(self._analizadores))


REGISTRO = RegistroAnalizadores()
