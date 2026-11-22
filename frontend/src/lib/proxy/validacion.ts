/**
 * Validaciones de la petición que llega del navegador al proxy.
 * El proxy añade el token del backend, así que también debe rechazar peticiones
 * de otros hosts u orígenes. Si no, cualquier página o red que alcance Next.js
 * podría usar el token indirectamente.
 */

const HOSTS_FRONTEND = new Set(["localhost:3000", "127.0.0.1:3000"]);
const ORIGENES_FRONTEND = new Set(["http://localhost:3000", "http://127.0.0.1:3000"]);

export type ResultadoValidacion = { ok: true } | { ok: false; motivo: string };

export function validarPeticionDelNavegador(peticion: Request): ResultadoValidacion {
  const host = peticion.headers.get("host");
  if (host === null || !HOSTS_FRONTEND.has(host)) {
    return { ok: false, motivo: "Host no permitido." };
  }

  const origen = peticion.headers.get("origin");
  if (origen !== null && !ORIGENES_FRONTEND.has(origen)) {
    return { ok: false, motivo: "Origen no permitido." };
  }

  // Las peticiones que modifican datos deben llegar con Origin. Así se bloquea CSRF desde otras páginas.
  if (peticion.method !== "GET" && origen === null) {
    return { ok: false, motivo: "Las peticiones de escritura requieren cabecera Origin." };
  }

  if (peticion.headers.get("sec-fetch-site") === "cross-site") {
    return { ok: false, motivo: "Petición de otro sitio no permitida." };
  }

  return { ok: true };
}
