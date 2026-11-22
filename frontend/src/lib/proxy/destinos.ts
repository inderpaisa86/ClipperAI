/** Un segmento de ruta solo puede tener letras, números, guion y guion bajo. */
const SEGMENTO_VALIDO = /^[a-z0-9_-]+$/i;

/** Un valor de consulta permitido: entero positivo sin ceros a la izquierda. */
const VALOR_ENTERO_POSITIVO = /^[1-9]\d{0,9}$/;

export type MetodoPermitido = "GET" | "POST" | "DELETE";

type DestinoPermitido = {
  metodo: MetodoPermitido;
  /** Coincide con la ruta relativa a /api/v1, sin barras al inicio ni al final. */
  patron: RegExp;
  /** Parámetros de consulta que el proxy reenvía. Cualquier otro se rechaza. */
  parametros?: readonly string[];
};

/**
 * Lista blanca explícita. El proxy solo reenvía lo que aparece aquí.
 * Para exponer un endpoint nuevo, se agrega una entrada y se registra en docs/decisiones.md.
 */
const DESTINOS_PERMITIDOS: readonly DestinoPermitido[] = [
  { metodo: "GET", patron: /^salud$/ },
  { metodo: "GET", patron: /^proyectos$/ },
  { metodo: "POST", patron: /^proyectos$/ },
  { metodo: "GET", patron: /^videos$/, parametros: ["proyecto_id"] },
  { metodo: "POST", patron: /^videos$/ },
  { metodo: "POST", patron: /^videos\/seleccion$/ },
  { metodo: "GET", patron: /^videos\/\d+$/ },
  { metodo: "DELETE", patron: /^videos\/\d+$/ },
  { metodo: "GET", patron: /^videos\/\d+\/stream$/ },
  { metodo: "GET", patron: /^jobs\/\d+$/ },
  { metodo: "POST", patron: /^jobs\/\d+\/cancelacion$/ },
];

export type ResultadoDestino =
  | { ok: true; rutaBackend: string }
  | { ok: false; estado: 400 | 404 | 405; motivo: string };

export function resolverDestino(
  metodo: string,
  segmentos: readonly string[],
  consulta: URLSearchParams,
): ResultadoDestino {
  if (segmentos.length === 0 || segmentos.some((segmento) => !SEGMENTO_VALIDO.test(segmento))) {
    return { ok: false, estado: 400, motivo: "La ruta solicitada no es válida." };
  }

  const ruta = segmentos.join("/");
  const coincidentes = DESTINOS_PERMITIDOS.filter((destino) => destino.patron.test(ruta));
  if (coincidentes.length === 0) {
    return { ok: false, estado: 404, motivo: "El destino no existe." };
  }

  const destino = coincidentes.find((candidato) => candidato.metodo === metodo);
  if (destino === undefined) {
    return { ok: false, estado: 405, motivo: "Método no permitido para este destino." };
  }

  const parametrosValidos = construirConsulta(consulta, destino.parametros ?? []);
  if (parametrosValidos === null) {
    return { ok: false, estado: 400, motivo: "Parámetros de consulta no válidos." };
  }

  return { ok: true, rutaBackend: `/api/v1/${ruta}${parametrosValidos}` };
}

/** Devuelve la cadena de consulta con solo los parámetros permitidos, o null si alguno no lo es. */
function construirConsulta(
  consulta: URLSearchParams,
  permitidos: readonly string[],
): string | null {
  const salida = new URLSearchParams();
  for (const [clave, valor] of consulta) {
    if (!permitidos.includes(clave) || !VALOR_ENTERO_POSITIVO.test(valor)) {
      return null;
    }
    salida.append(clave, valor);
  }
  const texto = salida.toString();
  return texto === "" ? "" : `?${texto}`;
}
