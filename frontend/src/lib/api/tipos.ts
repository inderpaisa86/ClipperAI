/** Espejo de los modelos de respuesta de FastAPI. Mantener sincronizado con backend/app/modules. */

export type PlataformaSalud = {
  sistema: string;
  arquitectura: string;
  cpus_logicas: number;
  apple_silicon: boolean;
};

export type HerramientaSalud = {
  disponible: boolean;
  version: string | null;
  mensaje: string | null;
};

export type EstadoSistema = "ok" | "degradado";

export type SaludRespuesta = {
  estado: EstadoSistema;
  plataforma: PlataformaSalud;
  ffmpeg: HerramientaSalud;
  ffprobe: HerramientaSalud;
  base_datos: "ok" | "error";
};

export type ErrorApiRespuesta = {
  detalle: string;
};

export type Proyecto = {
  id: number;
  nombre: string;
  creado: string;
};

export type Video = {
  id: number;
  proyecto_id: number;
  nombre: string;
  ruta: string;
  tamano_bytes: number;
  duracion_segundos: number | null;
  ancho: number;
  alto: number;
  fps: number | null;
  codec_video: string;
  codec_audio: string | null;
  formato: string;
  disponible: boolean;
  creado: string;
};

export type SeleccionArchivo = {
  ruta: string | null;
};
