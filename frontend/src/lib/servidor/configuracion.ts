import path from "node:path";

const URL_BACKEND_POR_DEFECTO = "http://127.0.0.1:8000";
const HOSTS_BACKEND_PERMITIDOS = new Set(["127.0.0.1", "localhost"]);

export type ConfiguracionServidor = {
  urlBackend: URL;
  rutaToken: string;
};

/**
 * Configuración exclusiva del servidor de Next.js.
 * Ninguna variable se lee con el prefijo NEXT_PUBLIC_, para que nunca llegue al navegador.
 * Este módulo importa node:fs (a través de token.ts), así que el build falla si un
 * componente de cliente lo importa.
 */
export function obtenerConfiguracion(): ConfiguracionServidor {
  const urlTexto = process.env.CLIPPERAI_BACKEND_URL ?? URL_BACKEND_POR_DEFECTO;
  const urlBackend = new URL(urlTexto);

  if (urlBackend.protocol !== "http:" || !HOSTS_BACKEND_PERMITIDOS.has(urlBackend.hostname)) {
    throw new Error("CLIPPERAI_BACKEND_URL debe apuntar a localhost mediante http.");
  }

  const directorioDatos =
    process.env.CLIPPERAI_DATA_DIR ?? path.resolve(process.cwd(), "..", "data");

  return {
    urlBackend,
    rutaToken: path.join(directorioDatos, "runtime", "sesion.token"),
  };
}
