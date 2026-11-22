import type { ErrorApiRespuesta, SaludRespuesta } from "./tipos";

/** Prefijo del proxy. El navegador nunca llama directamente al backend ni conoce su token. */
const PREFIJO_PROXY = "/api/backend";

export class ErrorApi extends Error {
  readonly estado: number;

  constructor(estado: number, mensaje: string) {
    super(mensaje);
    this.name = "ErrorApi";
    this.estado = estado;
  }
}

export type OpcionesSolicitud = {
  metodo?: "GET" | "POST" | "DELETE";
  cuerpo?: unknown;
  signal?: AbortSignal;
};

/**
 * Llama a un endpoint del backend a través del proxy.
 * `ruta` es relativa a /api/v1, por ejemplo "salud" o "videos?proyecto_id=3".
 */
export async function solicitarApi<T>(ruta: string, opciones: OpcionesSolicitud = {}): Promise<T> {
  const init: RequestInit = {
    method: opciones.metodo ?? "GET",
    cache: "no-store",
    signal: opciones.signal,
  };
  if (opciones.cuerpo !== undefined) {
    init.headers = { "Content-Type": "application/json" };
    init.body = JSON.stringify(opciones.cuerpo);
  }

  const respuesta = await fetch(`${PREFIJO_PROXY}/${ruta}`, init);

  if (!respuesta.ok) {
    let mensaje = `La solicitud falló con estado ${respuesta.status}.`;
    try {
      const cuerpo = (await respuesta.json()) as ErrorApiRespuesta;
      if (typeof cuerpo.detalle === "string") {
        mensaje = cuerpo.detalle;
      }
    } catch {
      // Respuesta sin JSON: se mantiene el mensaje genérico.
    }
    throw new ErrorApi(respuesta.status, mensaje);
  }

  if (respuesta.status === 204) {
    return undefined as T;
  }
  return (await respuesta.json()) as T;
}

export function obtenerSalud(signal?: AbortSignal): Promise<SaludRespuesta> {
  return solicitarApi<SaludRespuesta>("salud", { signal });
}
