/**
 * Reenvío de la petición validada al backend FastAPI.
 * Solo se copian cabeceras de una lista blanca, en ambos sentidos. El token se añade
 * aquí y nunca se devuelve al navegador ni aparece en mensajes de error.
 */

import type { MetodoPermitido } from "./destinos";

const CABECERAS_ENTRADA = ["accept", "range", "if-none-match", "content-type"] as const;

const CABECERAS_SALIDA = [
  "content-type",
  "content-length",
  "content-range",
  "accept-ranges",
  "etag",
  "last-modified",
] as const;

export function respuestaJsonError(estado: number, detalle: string): Response {
  return Response.json(
    { detalle },
    { status: estado, headers: { "Cache-Control": "no-store" } },
  );
}

export type OpcionesReenvio = {
  urlBackend: URL;
  rutaBackend: string;
  metodo: MetodoPermitido;
  peticion: Request;
  token: string;
  cuerpo: Uint8Array<ArrayBuffer> | null;
  /** Si se indica, una respuesta correcta del backend debe tener este tipo de contenido. */
  tipoEsperado?: string;
};

export async function reenviarAlBackend(opciones: OpcionesReenvio): Promise<Response> {
  const destino = new URL(opciones.rutaBackend, opciones.urlBackend);

  const cabeceras = new Headers();
  for (const nombre of CABECERAS_ENTRADA) {
    const valor = opciones.peticion.headers.get(nombre);
    if (valor !== null) {
      cabeceras.set(nombre, valor);
    }
  }
  cabeceras.set("X-ClipperAI-Token", opciones.token);

  let respuestaBackend: Response;
  try {
    // Sin cabecera Origin: el backend acepta peticiones sin Origin cuando el token es válido.
    // Host lo asigna fetch a partir de la URL, es decir 127.0.0.1:8000.
    respuestaBackend = await fetch(destino, {
      method: opciones.metodo,
      headers: cabeceras,
      body: opciones.cuerpo === null ? null : new Blob([opciones.cuerpo]),
      cache: "no-store",
      redirect: "error",
      signal: opciones.peticion.signal,
    });
  } catch {
    return respuestaJsonError(503, "El backend no está disponible.");
  }

  if (opciones.tipoEsperado !== undefined && respuestaBackend.ok) {
    const tipoRecibido = (respuestaBackend.headers.get("content-type") ?? "").toLowerCase();
    if (!tipoRecibido.startsWith(opciones.tipoEsperado)) {
      await respuestaBackend.body?.cancel();
      return respuestaJsonError(502, "El backend devolvió un contenido no esperado.");
    }
  }
  const cabecerasSalida = new Headers();
  for (const nombre of CABECERAS_SALIDA) {
    const valor = respuestaBackend.headers.get(nombre);
    if (valor !== null) {
      cabecerasSalida.set(nombre, valor);
    }
  }
  cabecerasSalida.set("Cache-Control", "no-store");

  return new Response(respuestaBackend.body, {
    status: respuestaBackend.status,
    headers: cabecerasSalida,
  });
}
