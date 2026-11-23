# Contrato de señales

Este documento describe el vocabulario cerrado de señales y los parámetros del analizador visual. La fuente de
verdad del vocabulario es `TIPOS_SENAL_PERMITIDOS` en `backend/app/plugins/contrato.py`. El proxy
(`frontend/src/lib/proxy/destinos.ts`) debe tener la misma lista, y una prueba lo verifica.

Reglas comunes:

- Todos los tiempos son enteros en milisegundos (D-033).
- `valor` y `confianza` están entre 0 y 1.
- Un intervalo `[inicio_ms, fin_ms]` puede tener duración cero. Una medida puntual se guarda con `inicio_ms = fin_ms`.

## Señales de audio (analizador `audio`, versión 1.0.0)

| Tipo | Significado | Unidad y escala | Interpretación del valor | Confianza | Muestreo |
|---|---|---|---|---|---|
| `energia_audio` | Nivel medio de una ventana de audio. | 0 a 1, donde 0 equivale a -90 dBFS o menos y 1 a 0 dBFS. | Valores altos indican sonido fuerte. | 1 | Ventanas de 200 ms. |
| `silencio` | Intervalo continuo sin sonido, de al menos 500 ms bajo el umbral del video. | 0 a 1 según cuánto baja el nivel bajo el umbral. | Valores altos indican silencio más profundo. | 1 | Por intervalo. |
| `cambio_intensidad` | Cambio de al menos 12 dB entre dos ventanas consecutivas. | 0 a 1, donde 24 dB equivalen a 1. | Valores altos indican un salto fuerte de volumen. | 1 | Par de ventanas de 400 ms. |

## Señales visuales (analizador `video`, versión 1.0.0)

| Tipo | Significado | Unidad y escala | Interpretación del valor | Confianza | Muestreo |
|---|---|---|---|---|---|
| `brillo` | Luminancia media del fotograma en gris. | 0 a 1, donde 0 es negro y 1 es blanco. | Cambios grandes entre muestras indican una variación fuerte de iluminación. | 1 (medición directa) | Un punto por muestra, cada `intervalo_muestreo_ms` (1 s). |
| `movimiento` | Fracción de píxeles que cambian más de 20 niveles de gris respecto a la muestra anterior. | 0 a 1. | 0 sin cambios visibles. Valores altos indican que gran parte de la imagen cambió. No distingue objetos ni personas. | 0,6 (diferencia entre fotogramas; no separa el movimiento de la cámara del de los objetos) | Intervalo entre muestras consecutivas (1 s). |
| `cambio_escena` | Corte o cambio visual brusco. Se registra cuando la fracción de píxeles que cambian más de 30 niveles de gris llega a 0,35, y han pasado al menos 2 s desde la detección anterior. | 0,35 a 1. Es la fracción de píxeles cambiados. | Valores cercanos a 1 indican un corte completo. Valores cerca de 0,35 indican un cambio parcial. | 0,8 (método clásico; fiable en cortes, no en fundidos lentos) | Intervalo entre muestras consecutivas (1 s). |

Los tipos visuales no incluyen ninguna clasificación semántica. El vocabulario se amplió en la Etapa 4 (D-058
a D-062) siguiendo el procedimiento de D-052.

## Parámetros configurables del analizador visual

Están centralizados en `backend/app/modules/vision/parametros.py`. Cambiar uno cambia los resultados, así que exige
subir la versión del analizador (D-015).

| Parámetro | Valor por defecto | Descripción |
|---|---|---|
| `intervalo_muestreo_ms` | 1000 | Separación de la cuadrícula de muestras. |
| `duracion_segmento_ms` | 60000 | Duración de cada segmento de trabajo. |
| `hilos_ffmpeg` | 8 | Hilos de decodificación de FFmpeg. Valor medido en la Etapa 0 (D-031). |
| `ancho_fotograma` | 320 | Ancho máximo de la imagen decodificada y de las miniaturas. Conserva la relación de aspecto. |
| `ancho_analisis` | 160 | Ancho de la copia en gris sobre la que se miden las señales. |
| `umbral_pixel_cambio_escena` | 30 | Diferencia de gris que cuenta como píxel cambiado para `cambio_escena`. |
| `umbral_fraccion_escena` | 0,35 | Fracción de píxeles cambiados que declara un corte. |
| `intervalo_minimo_escena_ms` | 2000 | Distancia mínima entre dos detecciones de `cambio_escena`. |
| `umbral_pixel_movimiento` | 20 | Diferencia de gris que cuenta como píxel cambiado para `movimiento`. |
| `maximo_fotogramas_por_minuto` | 6 | Límite de fotogramas representativos por minuto de video. |
| `umbral_movimiento_destacado` | 0,10 | Movimiento mínimo para que un fotograma sea candidato a representativo. |
| `separacion_minima_fotogramas_ms` | 5000 | Distancia mínima entre fotogramas representativos. |
| `diferencia_minima_fotogramas` | 0,05 | Distancia mínima entre huellas visuales de dos fotogramas representativos. |
| `calidad_jpeg` | 85 | Calidad de las miniaturas JPEG. |
| `confianza_cambio_escena` | 0,8 | Confianza fija del método de escena. |
| `confianza_movimiento` | 0,6 | Confianza fija del método de movimiento. |
| `confianza_brillo` | 1,0 | Confianza fija de la medición de brillo. |

## Limitaciones del análisis clásico

- Un movimiento rápido de la cámara puede parecer un corte si cambia más de 35 % de los píxeles.
- Un fundido lento entre escenas puede no alcanzar el umbral de escena. Sus cambios aparecen en `brillo`, no en `cambio_escena`.
- Las medidas no distinguen un objeto de otro, ni a una persona de un fondo.
- El tiempo de cada muestra es el de la cuadrícula. Su error es como máximo una duración de fotograma del video.
- Un video con rotación en sus metadatos puede medirse con la relación de aspecto invertida, porque el tamaño de la
  imagen sale de la base de datos y no se corrige la rotación.
- Los resultados dependen de la resolución y del muestreo. Cambiar cualquier parámetro exige reanalizar el video.
