"use client";

import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";

import { crearProyecto, listarProyectos } from "@/lib/api/proyectos";
import type { Proyecto } from "@/lib/api/tipos";

import { formatearFecha } from "../videos/formato";

export function PanelProyectos() {
  const [proyectos, setProyectos] = useState<Proyecto[] | null>(null);
  const [nombre, setNombre] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [guardando, setGuardando] = useState(false);

  useEffect(() => {
    let activo = true;
    listarProyectos()
      .then((lista) => {
        if (activo) setProyectos(lista);
      })
      .catch((err: unknown) => {
        if (activo) setError(mensajeDe(err));
      });
    return () => {
      activo = false;
    };
  }, []);

  async function enviar(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    setError(null);
    setGuardando(true);
    try {
      const creado = await crearProyecto(nombre);
      setProyectos((actuales) => [...(actuales ?? []), creado]);
      setNombre("");
    } catch (err) {
      setError(mensajeDe(err));
    } finally {
      setGuardando(false);
    }
  }

  const totalVideos = proyectos?.reduce((suma, proyecto) => suma + proyecto.cantidad_videos, 0) ?? 0;

  return (
    <>
      <header className="encabezado-pagina">
        <div>
          <h1>Proyectos</h1>
          <p className="texto-secundario">
            Agrupe los videos que ClipperAI analizará y revise los clips de cada proyecto.
          </p>
        </div>
        {proyectos !== null && (
          <dl className="resumen" aria-label="Resumen de proyectos y videos">
            <div className="estadistica">
              <dt>Proyectos</dt>
              <dd>{proyectos.length}</dd>
            </div>
            <div className="estadistica">
              <dt>Videos</dt>
              <dd>{totalVideos}</dd>
            </div>
          </dl>
        )}
      </header>

      <section className="tarjeta" aria-labelledby="titulo-nuevo-proyecto">
        <h2 id="titulo-nuevo-proyecto">Nuevo proyecto</h2>
        <form className="formulario en-linea" onSubmit={enviar}>
          <label htmlFor="nombre-proyecto">Nombre del proyecto</label>
          <input
            id="nombre-proyecto"
            type="text"
            value={nombre}
            onChange={(e) => setNombre(e.target.value)}
            maxLength={120}
            required
          />
          <button className="boton" type="submit" disabled={guardando || nombre.trim() === ""}>
            {guardando ? "Creando…" : "Crear proyecto"}
          </button>
        </form>
        {error !== null && <p className="mensaje-error" role="alert">{error}</p>}
      </section>

      {proyectos === null && error === null && <p className="texto-secundario">Cargando…</p>}

      {proyectos !== null && proyectos.length === 0 && (
        <section className="vacio" aria-live="polite">
          <h2>Todavía no hay proyectos</h2>
          <p className="texto-secundario">
            Cree el primero con el formulario de arriba. Después podrá importar videos dentro de él.
          </p>
        </section>
      )}

      {proyectos !== null && proyectos.length > 0 && (
        <section aria-labelledby="titulo-lista-proyectos" className="seccion-proyectos">
          <h2 id="titulo-lista-proyectos" className="titulo-seccion">
            Sus proyectos
          </h2>
          <ul className="cuadricula-proyectos">
            {proyectos.map((proyecto) => (
              <li key={proyecto.id}>
                <Link href={`/proyectos/${proyecto.id}`} className="tarjeta-proyecto">
                  <span className="nombre-proyecto">{proyecto.nombre}</span>
                  <span className={`insignia ${proyecto.cantidad_videos > 0 ? "acento" : "neutral"}`}>
                    {textoVideos(proyecto.cantidad_videos)}
                  </span>
                  <span className="texto-secundario">
                    Creado el {formatearFecha(proyecto.creado)}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}

function textoVideos(cantidad: number): string {
  if (cantidad === 0) return "Sin videos";
  return cantidad === 1 ? "1 video" : `${cantidad} videos`;
}

function mensajeDe(error: unknown): string {
  return error instanceof Error ? error.message : "Error inesperado.";
}
