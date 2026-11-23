"use client";

import { useState } from "react";

import { urlStreamVideo } from "@/lib/api/videos";
import type { Video } from "@/lib/api/tipos";

import { formatearBytes, formatearDuracion, formatearFps, formatearResolucion } from "./formato";

type Props = {
  video: Video;
  onEliminar: (video: Video) => void;
};

export function DetalleVideo({ video, onEliminar }: Props) {
  const [errorReproduccion, setErrorReproduccion] = useState<string | null>(null);

  function confirmarEliminacion() {
    const confirmado = window.confirm(
      "Se eliminará el registro del video en ClipperAI. El archivo original no se modificará ni se borrará. ¿Desea continuar?",
    );
    if (confirmado) {
      onEliminar(video);
    }
  }

  return (
    <section className="tarjeta detalle-video" aria-labelledby="titulo-detalle">
      <h3 id="titulo-detalle">{video.nombre}</h3>

      {video.disponible ? (
        <>
          <video
            className="reproductor"
            controls
            preload="metadata"
            src={urlStreamVideo(video.id)}
            onError={() =>
              setErrorReproduccion(
                "El navegador no puede reproducir este archivo. Los metadatos siguen disponibles.",
              )
            }
            onPlaying={() => setErrorReproduccion(null)}
          />
          {errorReproduccion !== null && (
            <p className="texto-secundario" role="status">{errorReproduccion}</p>
          )}
        </>
      ) : (
        <p className="mensaje-error" role="alert">
          El archivo original ya no está en su ruta. El registro se conserva hasta que lo elimine.
        </p>
      )}

      <dl className="detalles">
        <dt>Archivo original</dt>
        <dd className="ruta">{video.nombre_archivo}</dd>

        <dt>Tamaño</dt>
        <dd>{formatearBytes(video.tamano_bytes)}</dd>

        <dt>Duración</dt>
        <dd>{formatearDuracion(video.duracion_segundos)}</dd>

        <dt>Resolución</dt>
        <dd>{formatearResolucion(video.ancho, video.alto)}</dd>

        <dt>FPS</dt>
        <dd>{formatearFps(video.fps)}</dd>

        <dt>Códec de video</dt>
        <dd>{video.codec_video}</dd>

        <dt>Códec de audio</dt>
        <dd>{video.codec_audio ?? "Sin audio"}</dd>

        <dt>Formato</dt>
        <dd>{video.formato}</dd>
      </dl>

      <div className="fila-acciones">
        <button className="boton peligro" type="button" onClick={confirmarEliminacion}>
          Eliminar registro
        </button>
      </div>
    </section>
  );
}
