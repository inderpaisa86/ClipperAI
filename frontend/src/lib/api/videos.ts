import { solicitarApi } from "./cliente";
import type { OrigenVideo, SeleccionArchivo, Video } from "./tipos";

export function listarVideos(proyectoId: number): Promise<Video[]> {
  return solicitarApi<Video[]>(`videos?proyecto_id=${proyectoId}`);
}

export function importarVideo(proyectoId: number, origen: OrigenVideo): Promise<Video> {
  return solicitarApi<Video>("videos", {
    metodo: "POST",
    cuerpo: { proyecto_id: proyectoId, ...origen },
  });
}

/** Abre el selector nativo del sistema. Devuelve ruta null si el usuario cancela. */
export function seleccionarArchivo(): Promise<SeleccionArchivo> {
  return solicitarApi<SeleccionArchivo>("videos/seleccion", { metodo: "POST" });
}

export function eliminarVideo(videoId: number): Promise<void> {
  return solicitarApi<void>(`videos/${videoId}`, { metodo: "DELETE" });
}

/** URL de transmisión a través del proxy. El reproductor del navegador envía cabeceras Range. */
export function urlStreamVideo(videoId: number): string {
  return `/api/backend/videos/${videoId}/stream`;
}
