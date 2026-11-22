/** Tamaño máximo de un cuerpo JSON que el proxy acepta. Los videos nunca viajan por aquí. */
export const LIMITE_CUERPO_BYTES = 64 * 1024;

export class CuerpoDemasiadoGrande extends Error {
  constructor() {
    super("El cuerpo de la petición es demasiado grande.");
    this.name = "CuerpoDemasiadoGrande";
  }
}

/**
 * Lee el cuerpo de la petición con un límite estricto, sin confiar en Content-Length.
 * Devuelve null si el cuerpo está vacío.
 */
export async function leerCuerpoLimitado(
  peticion: Request,
  limite: number = LIMITE_CUERPO_BYTES,
): Promise<Uint8Array<ArrayBuffer> | null> {
  const declarado = Number(peticion.headers.get("content-length") ?? "0");
  if (declarado > limite) {
    throw new CuerpoDemasiadoGrande();
  }
  if (peticion.body === null) {
    return null;
  }

  const lector = peticion.body.getReader();
  const trozos: Uint8Array[] = [];
  let total = 0;
  for (;;) {
    const { done, value } = await lector.read();
    if (done) {
      break;
    }
    total += value.byteLength;
    if (total > limite) {
      await lector.cancel();
      throw new CuerpoDemasiadoGrande();
    }
    trozos.push(value);
  }

  if (total === 0) {
    return null;
  }

  const unido = new Uint8Array(new ArrayBuffer(total));
  let desplazamiento = 0;
  for (const trozo of trozos) {
    unido.set(trozo, desplazamiento);
    desplazamiento += trozo.byteLength;
  }
  return unido;
}
