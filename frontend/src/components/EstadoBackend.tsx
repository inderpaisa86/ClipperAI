"use client";

import { useEffect, useState } from "react";

import { ErrorApi, obtenerSalud } from "@/lib/api/cliente";
import type { SaludRespuesta } from "@/lib/api/tipos";

/** Intervalo de polling acordado en D-010. */
const INTERVALO_MS = 2000;

type Estado =
  | { fase: "comprobando" }
  | { fase: "conectado"; salud: SaludRespuesta }
  | { fase: "sin_conexion"; mensaje: string };

/** Muestra "ffmpeg version 9.1-full_build-www.gyan.dev ..." como "9.1-full_build-www.gyan.dev". */
function versionCorta(linea: string): string {
  return linea.match(/version\s+(\S+)/)?.[1] ?? linea;
}

function mensajeDeError(error: unknown): string {
  if (error instanceof ErrorApi) {
    return error.message;
  }
  return "No se pudo contactar con el servidor local. Verifique que el backend esté en ejecución.";
}

export function EstadoBackend() {
  const [estado, setEstado] = useState<Estado>({ fase: "comprobando" });

  useEffect(() => {
    let activo = true;
    let controlador: AbortController | null = null;

    async function comprobar() {
      controlador?.abort();
      controlador = new AbortController();
      try {
        const salud = await obtenerSalud(controlador.signal);
        if (activo) {
          setEstado({ fase: "conectado", salud });
        }
      } catch (error) {
        const cancelado = error instanceof DOMException && error.name === "AbortError";
        if (activo && !cancelado) {
          setEstado({ fase: "sin_conexion", mensaje: mensajeDeError(error) });
        }
      }
    }

    comprobar();
    const temporizador = window.setInterval(comprobar, INTERVALO_MS);

    return () => {
      activo = false;
      window.clearInterval(temporizador);
      controlador?.abort();
    };
  }, []);

  const conexion =
    estado.fase === "conectado"
      ? { texto: "Conectado", clase: "ok" }
      : estado.fase === "sin_conexion"
        ? { texto: "Sin conexión", clase: "error" }
        : { texto: "Comprobando…", clase: "neutral" };

  const disponibilidad =
    estado.fase !== "conectado"
      ? null
      : estado.salud.estado === "ok"
        ? { texto: "Sistema listo", clase: "ok" }
        : { texto: "Sistema con limitaciones", clase: "aviso" };

  return (
    <section className="tarjeta" aria-labelledby="titulo-estado">
      <h2 id="titulo-estado">Estado del sistema</h2>

      <div className="indicadores" role="status">
        <div className="indicador">
          <span className="etiqueta">Conexión con el backend</span>
          <span className={`insignia ${conexion.clase}`}>{conexion.texto}</span>
        </div>
        {disponibilidad !== null && (
          <div className="indicador">
            <span className="etiqueta">Disponibilidad</span>
            <span className={`insignia ${disponibilidad.clase}`}>{disponibilidad.texto}</span>
          </div>
        )}
      </div>

      {estado.fase === "sin_conexion" && <p className="mensaje-error">{estado.mensaje}</p>}

      {estado.fase === "conectado" && (
        <dl className="detalles">
          <dt>Plataforma</dt>
          <dd>
            {estado.salud.plataforma.sistema} · {estado.salud.plataforma.arquitectura} ·{" "}
            {estado.salud.plataforma.cpus_logicas} hilos
          </dd>

          <dt>FFmpeg</dt>
          <dd>
            {estado.salud.ffmpeg.disponible && estado.salud.ffmpeg.version
              ? versionCorta(estado.salud.ffmpeg.version)
              : (estado.salud.ffmpeg.mensaje ?? "No disponible")}
          </dd>

          <dt>FFprobe</dt>
          <dd>
            {estado.salud.ffprobe.disponible && estado.salud.ffprobe.version
              ? versionCorta(estado.salud.ffprobe.version)
              : (estado.salud.ffprobe.mensaje ?? "No disponible")}
          </dd>

          <dt>Base de datos</dt>
          <dd>{estado.salud.base_datos === "ok" ? "Operativa" : "Con error"}</dd>
        </dl>
      )}
    </section>
  );
}
