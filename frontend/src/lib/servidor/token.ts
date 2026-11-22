import { promises as fs } from "node:fs";

import { obtenerConfiguracion } from "./configuracion";

const LONGITUD_MINIMA_TOKEN = 43;

export class TokenNoDisponible extends Error {
  constructor() {
    super("El backend no ha generado un token de sesión. Arranque el backend primero.");
    this.name = "TokenNoDisponible";
  }
}

/**
 * Lee el token en cada petición. El backend genera un token nuevo en cada arranque,
 * así que no conviene cachearlo. El valor nunca se registra ni se devuelve al cliente.
 */
export async function leerTokenSesion(): Promise<string> {
  const { rutaToken } = obtenerConfiguracion();

  let contenido: string;
  try {
    contenido = await fs.readFile(rutaToken, "utf-8");
  } catch {
    throw new TokenNoDisponible();
  }

  const token = contenido.trim();
  if (token.length < LONGITUD_MINIMA_TOKEN) {
    throw new TokenNoDisponible();
  }
  return token;
}
