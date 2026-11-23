/** Un segmento de ruta solo puede tener letras, números, guion y guion bajo. */
const SEGMENTO_VALIDO = /^[a-z0-9_-]+$/i;

/**
 * Vocabulario cerrado de tipos de señal. Debe coincidir con TIPOS_SENAL_PERMITIDOS en
 * backend/app/plugins/contrato.py. La prueba test_vocabulario_coincide_con_el_proxy lo verifica.
 */
export const TIPOS_SENAL_PERMITIDOS = [
  "energia_audio",
  "silencio",
  "cambio_intensidad",
  "cambio_escena",
  "movimiento",
  "brillo",
] as const;

/** Tipos de valor que admite un parámetro de consulta. Ninguno admite signo ni decimales. */
export type TipoParametro = "entero_positivo" | "entero_no_negativo" | "tipo_senal";

const VALIDADORES: Readonly<Record<TipoParametro, (valor: string) => boolean>> = {
  /** Entero positivo sin ceros a la izquierda. */
  entero_positivo: (valor) => /^[1-9]\d{0,9}$/.test(valor),
  /** Cero o entero positivo sin ceros a la izquierda. */
  entero_no_negativo: (valor) => /^(0|[1-9]\d{0,9})$/.test(valor),
  /** Uno de los tipos del vocabulario cerrado. */
  tipo_senal: (valor) => (TIPOS_SENAL_PERMITIDOS as readonly string[]).includes(valor),
};

export type MetodoPermitido = "GET" | "POST" | "DELETE";

type DestinoPermitido = {
  metodo: MetodoPermitido;
  /** Coincide con la ruta relativa a /api/v1, sin barras al inicio ni al final. */
  patron: RegExp;
  /** Parámetros de consulta que el proxy reenvía, con su tipo de valor. Cualquier otro se rechaza. */
  parametros?: Readonly<Record<string, TipoParametro>>;
  /** Tipo de contenido que el backend debe devolver cuando responde con éxito. Si falta, no se fuerza ninguno. */
  tipoRespuesta?: string;
};

/** Identificador de analizador: letra inicial, después minúsculas, números o guion bajo. */
const ANALIZADOR = "[a-z][a-z0-9_]{0,31}";

/**
 * Lista blanca explícita. El proxy solo reenvía lo que aparece aquí.
 * Para exponer un endpoint nuevo, se agrega una entrada y se registra en docs/decisiones.md.
 */
const DESTINOS_PERMITIDOS: readonly DestinoPermitido[] = [
  { metodo: "GET", patron: /^salud$/ },
  { metodo: "GET", patron: /^proyectos$/ },
  { metodo: "POST", patron: /^proyectos$/ },
  { metodo: "GET", patron: /^videos$/, parametros: { proyecto_id: "entero_positivo" } },
  { metodo: "POST", patron: /^videos$/ },
  { metodo: "POST", patron: /^videos\/seleccion$/ },
  { metodo: "GET", patron: /^videos\/\d+$/ },
  { metodo: "DELETE", patron: /^videos\/\d+$/ },
  { metodo: "GET", patron: /^videos\/\d+\/stream$/ },
  { metodo: "GET", patron: /^jobs\/\d+$/ },
  { metodo: "POST", patron: /^jobs\/\d+\/cancelacion$/ },
  { metodo: "GET", patron: new RegExp(`^videos\\/\\d+\\/analisis$`) },
  { metodo: "POST", patron: new RegExp(`^videos\\/\\d+\\/analisis$`) },
  { metodo: "GET", patron: new RegExp(`^videos\\/\\d+\\/analisis\\/${ANALIZADOR}$`) },
  {
    metodo: "GET",
    patron: new RegExp(`^videos\\/\\d+\\/analisis\\/${ANALIZADOR}\\/senales$`),
    parametros: {
      inicio_ms: "entero_no_negativo",
      fin_ms: "entero_no_negativo",
      limite: "entero_positivo",
      tipo: "tipo_senal",
    },
  },
  {
    metodo: "GET",
    patron: new RegExp(`^videos\\/\\d+\\/analisis\\/${ANALIZADOR}\\/fotogramas$`),
    parametros: { limite: "entero_positivo" },
  },
  {
    metodo: "GET",
    patron: new RegExp(`^videos\\/\\d+\\/analisis\\/${ANALIZADOR}\\/fotogramas\\/\\d+\\/miniatura$`),
    tipoRespuesta: "image/jpeg",
  },
];

export type ResultadoDestino =
  | { ok: true; rutaBackend: string; tipoRespuesta?: string }
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

  const parametrosValidos = construirConsulta(consulta, destino.parametros ?? {});
  if (parametrosValidos === null) {
    return { ok: false, estado: 400, motivo: "Parámetros de consulta no válidos." };
  }

  return {
    ok: true,
    rutaBackend: `/api/v1/${ruta}${parametrosValidos}`,
    ...(destino.tipoRespuesta !== undefined ? { tipoRespuesta: destino.tipoRespuesta } : {}),
  };
}

/** Devuelve la cadena de consulta con solo los parámetros permitidos, o null si alguno no lo es. */
function construirConsulta(
  consulta: URLSearchParams,
  permitidos: Readonly<Record<string, TipoParametro>>,
): string | null {
  const salida = new URLSearchParams();
  for (const [clave, valor] of consulta) {
    const tipo = Object.prototype.hasOwnProperty.call(permitidos, clave) ? permitidos[clave] : undefined;
    if (tipo === undefined || !VALIDADORES[tipo](valor)) {
      return null;
    }
    salida.append(clave, valor);
  }
  const texto = salida.toString();
  return texto === "" ? "" : `?${texto}`;
}
