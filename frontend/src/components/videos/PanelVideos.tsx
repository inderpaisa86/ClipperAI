"use client";

import { useEffect, useState } from "react";

import { eliminarVideo, listarVideos } from "@/lib/api/videos";
import type { Video } from "@/lib/api/tipos";

import { DetalleVideo } from "./DetalleVideo";
import { ImportarVideo } from "./ImportarVideo";
import { formatearBytes, formatearDuracion, formatearFps, formatearResolucion } from "./formato";

type Props = {
  proyectoId: number;
};

export function PanelVideos({ proyectoId }: Props) {
  const [videos, setVideos] = useState<Video[] | null>(null);
  const [seleccionadoId, setSeleccionadoId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let activo = true;
    listarVideos(proyectoId)
      .then((lista) => {
        if (activo) setVideos(lista);
      })
      .catch((err: unknown) => {
        if (activo) setError(mensajeDe(err));
      });
    return () => {
      activo = false;
    };
  }, [proyectoId]);

  function alImportar(video: Video) {
    setVideos((actuales) => [...(actuales ?? []), video]);
    setSeleccionadoId(video.id);
  }

  async function alEliminar(video: Video) {
    setError(null);
    try {
      await eliminarVideo(video.id);
      setVideos((actuales) => (actuales ?? []).filter((v) => v.id !== video.id));
      setSeleccionadoId((actual) => (actual === video.id ? null : actual));
    } catch (err) {
      setError(mensajeDe(err));
    }
  }

  const seleccionado = videos?.find((video) => video.id === seleccionadoId) ?? null;

  return (
    <section className="tarjeta" aria-labelledby="titulo-videos">
      <h2 id="titulo-videos">Videos del proyecto</h2>

      <ImportarVideo
        proyectoId={proyectoId}
        onImportado={alImportar}
        onError={(mensaje) => setError(mensaje === "" ? null : mensaje)}
      />

      {error !== null && <p className="mensaje-error" role="alert">{error}</p>}

      {videos === null && error === null && <p className="texto-secundario">Cargando…</p>}

      {videos !== null && videos.length === 0 && (
        <p className="texto-secundario">Este proyecto todavía no tiene videos.</p>
      )}

      {videos !== null && videos.length > 0 && (
        <div className="tabla-contenedor">
          <table className="tabla">
            <thead>
              <tr>
                <th scope="col">Nombre</th>
                <th scope="col">Resolución</th>
                <th scope="col">Duración</th>
                <th scope="col">FPS</th>
                <th scope="col">Códec</th>
                <th scope="col">Tamaño</th>
                <th scope="col">Estado</th>
                <th scope="col"><span className="sr-only">Acciones</span></th>
              </tr>
            </thead>
            <tbody>
              {videos.map((video) => (
                <tr key={video.id} className={video.id === seleccionadoId ? "fila-activa" : undefined}>
                  <td>{video.nombre}</td>
                  <td>{formatearResolucion(video.ancho, video.alto)}</td>
                  <td>{formatearDuracion(video.duracion_segundos)}</td>
                  <td>{formatearFps(video.fps)}</td>
                  <td>{video.codec_video}</td>
                  <td>{formatearBytes(video.tamano_bytes)}</td>
                  <td>
                    <span className={`insignia ${video.disponible ? "ok" : "error"}`}>
                      {video.disponible ? "Disponible" : "No disponible"}
                    </span>
                  </td>
                  <td>
                    <button
                      className="boton secundario pequeno"
                      type="button"
                      onClick={() => setSeleccionadoId(video.id)}
                    >
                      Ver
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {seleccionado !== null && (
        <DetalleVideo key={seleccionado.id} video={seleccionado} onEliminar={alEliminar} />
      )}
    </section>
  );
}

function mensajeDe(error: unknown): string {
  return error instanceof Error ? error.message : "Error inesperado.";
}
