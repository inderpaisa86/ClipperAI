import { resolverDestino, type MetodoPermitido } from "@/lib/proxy/destinos";
import { CuerpoDemasiadoGrande, leerCuerpoLimitado } from "@/lib/proxy/cuerpo";
import { reenviarAlBackend, respuestaJsonError } from "@/lib/proxy/reenvio";
import { validarPeticionDelNavegador } from "@/lib/proxy/validacion";
import { obtenerConfiguracion } from "@/lib/servidor/configuracion";
import { leerTokenSesion, TokenNoDisponible } from "@/lib/servidor/token";

/** El token cambia con cada arranque del backend, así que la respuesta nunca se reutiliza. */
export const dynamic = "force-dynamic";

type Contexto = { params: Promise<{ ruta: string[] }> };

async function gestionarPeticion(peticion: Request, contexto: Contexto): Promise<Response> {
  const validacion = validarPeticionDelNavegador(peticion);
  if (!validacion.ok) {
    return respuestaJsonError(403, validacion.motivo);
  }

  const { ruta } = await contexto.params;
  const url = new URL(peticion.url);
  const destino = resolverDestino(peticion.method, ruta, url.searchParams);
  if (!destino.ok) {
    return respuestaJsonError(destino.estado, destino.motivo);
  }

  let cuerpo: Uint8Array<ArrayBuffer> | null = null;
  if (peticion.method === "POST") {
    try {
      cuerpo = await leerCuerpoLimitado(peticion);
    } catch (error) {
      if (error instanceof CuerpoDemasiadoGrande) {
        return respuestaJsonError(413, error.message);
      }
      return respuestaJsonError(400, "No se pudo leer el cuerpo de la petición.");
    }
    const tipo = peticion.headers.get("content-type") ?? "";
    if (cuerpo !== null && !tipo.toLowerCase().startsWith("application/json")) {
      return respuestaJsonError(415, "El cuerpo debe enviarse como application/json.");
    }
  }

  let urlBackend: URL;
  try {
    urlBackend = obtenerConfiguracion().urlBackend;
  } catch {
    return respuestaJsonError(500, "La configuración del proxy no es válida.");
  }

  let token: string;
  try {
    token = await leerTokenSesion();
  } catch (error) {
    if (error instanceof TokenNoDisponible) {
      return respuestaJsonError(503, error.message);
    }
    return respuestaJsonError(500, "No se pudo leer la sesión del backend.");
  }

  return reenviarAlBackend({
    urlBackend,
    rutaBackend: destino.rutaBackend,
    metodo: peticion.method as MetodoPermitido,
    peticion,
    token,
    cuerpo,
  });
}

export function GET(peticion: Request, contexto: Contexto): Promise<Response> {
  return gestionarPeticion(peticion, contexto);
}

export function POST(peticion: Request, contexto: Contexto): Promise<Response> {
  return gestionarPeticion(peticion, contexto);
}

export function DELETE(peticion: Request, contexto: Contexto): Promise<Response> {
  return gestionarPeticion(peticion, contexto);
}
