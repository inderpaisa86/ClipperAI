class ErrorAplicacion(Exception):
    """Error de dominio con el estado HTTP que le corresponde. Lo traduce main.py."""

    estado: int = 500

    def __init__(self, mensaje: str) -> None:
        super().__init__(mensaje)
        self.mensaje = mensaje


class SolicitudInvalida(ErrorAplicacion):
    estado = 422


class NoEncontrado(ErrorAplicacion):
    estado = 404


class Conflicto(ErrorAplicacion):
    estado = 409


class NoSoportado(ErrorAplicacion):
    estado = 501


class NoDisponible(ErrorAplicacion):
    estado = 503
