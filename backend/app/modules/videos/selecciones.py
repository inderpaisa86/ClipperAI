"""Selecciones pendientes del selector nativo.

El selector devuelve al navegador un identificador opaco y el nombre del archivo. La ruta absoluta
queda solo en memoria del backend. Cada selección sirve una vez y caduca a los 10 minutos.
"""

import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

DURACION_SELECCION_SEGUNDOS = 600.0
MAXIMO_SELECCIONES = 16


@dataclass(frozen=True)
class _Seleccion:
    ruta: Path
    vence: float


class RegistroSelecciones:
    def __init__(self, reloj: Callable[[], float] = time.monotonic) -> None:
        self._reloj = reloj
        self._bloqueo = threading.Lock()
        self._entradas: dict[str, _Seleccion] = {}

    def guardar(self, ruta: Path) -> str:
        """Guarda la ruta elegida y devuelve su identificador. Descarta las más antiguas si hay demasiadas."""
        identificador = secrets.token_urlsafe(16)
        with self._bloqueo:
            self._purgar()
            while len(self._entradas) >= MAXIMO_SELECCIONES:
                mas_antigua = min(self._entradas, key=lambda clave: self._entradas[clave].vence)
                del self._entradas[mas_antigua]
            self._entradas[identificador] = _Seleccion(
                ruta=ruta, vence=self._reloj() + DURACION_SELECCION_SEGUNDOS
            )
        return identificador

    def tomar(self, identificador: str) -> Path | None:
        """Devuelve la ruta y la retira del registro. None si caducó, ya se usó o no existe."""
        with self._bloqueo:
            self._purgar()
            entrada = self._entradas.pop(identificador, None)
        return None if entrada is None else entrada.ruta

    def _purgar(self) -> None:
        ahora = self._reloj()
        for clave in [clave for clave, entrada in self._entradas.items() if entrada.vence <= ahora]:
            del self._entradas[clave]
