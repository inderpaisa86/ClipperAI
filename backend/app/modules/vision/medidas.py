"""Medidas clásicas de OpenCV sobre fotogramas. Son funciones puras, sin acceso a archivos ni a la base.

Todas las medidas se normalizan a 0-1. Ninguna interpreta el contenido de la imagen: solo compara niveles
de gris, píxel a píxel, entre fotogramas consecutivos (D-059).
"""
import cv2
import numpy as np

from app.modules.vision.captura import ErrorVideo

FIRMA_ANCHO = 16
FIRMA_ALTO = 9
NIVELES_GRIS = 255.0


def reducir_gris(imagen_bgr: np.ndarray, ancho: int, alto: int) -> np.ndarray:
    gris = cv2.cvtColor(imagen_bgr, cv2.COLOR_BGR2GRAY)
    return cv2.resize(gris, (ancho, alto), interpolation=cv2.INTER_AREA)


def brillo(gris: np.ndarray) -> float:
    """Luminancia media del fotograma, de 0 (negro) a 1 (blanco)."""
    return float(gris.mean()) / NIVELES_GRIS


def fracciones_cambiadas(
    gris_anterior: np.ndarray, gris_actual: np.ndarray, umbral_a: int, umbral_b: int
) -> tuple[float, float]:
    """Fracción de píxeles cuya diferencia de gris supera cada umbral. Devuelve (fracción_a, fracción_b).

    Calcula la diferencia una sola vez. Un píxel que cambia poco, por ruido de compresión, no cuenta.
    """
    diferencia = cv2.absdiff(gris_anterior, gris_actual)
    total = float(diferencia.size)
    return (
        float(np.count_nonzero(diferencia >= umbral_a)) / total,
        float(np.count_nonzero(diferencia >= umbral_b)) / total,
    )


def firma(imagen_bgr: np.ndarray) -> np.ndarray:
    """Huella visual pequeña de un fotograma: 16 x 9 niveles de gris normalizados. Sirve para comparar."""
    gris = cv2.cvtColor(imagen_bgr, cv2.COLOR_BGR2GRAY)
    pequena = cv2.resize(gris, (FIRMA_ANCHO, FIRMA_ALTO), interpolation=cv2.INTER_AREA)
    return pequena.astype(np.float32).reshape(-1) / NIVELES_GRIS


def distancia_firmas(primera: np.ndarray, segunda: np.ndarray) -> float:
    """Diferencia media entre dos firmas, de 0 (iguales) a 1."""
    return float(np.mean(np.abs(primera - segunda)))


def codificar_jpeg(imagen_bgr: np.ndarray, calidad: int) -> bytes:
    correcto, bytes_jpeg = cv2.imencode(".jpg", imagen_bgr, [cv2.IMWRITE_JPEG_QUALITY, calidad])
    if not correcto:
        raise ErrorVideo("No se pudo codificar un fotograma.")
    return bytes_jpeg.tobytes()


def decodificar_jpeg(datos: bytes) -> np.ndarray:
    imagen = cv2.imdecode(np.frombuffer(datos, dtype=np.uint8), cv2.IMREAD_COLOR)
    if imagen is None:
        raise ErrorVideo("Una miniatura guardada no se puede leer.")
    return imagen
