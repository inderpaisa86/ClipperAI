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

  return (
    <section className="tarjeta" aria-labelledby="titulo-proyectos">
      <h2 id="titulo-proyectos">Proyectos</h2>

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

      {proyectos === null && error === null && <p className="texto-secundario">Cargando…</p>}

      {proyectos !== null && proyectos.length === 0 && (
        <p className="texto-secundario">Todavía no hay proyectos. Cree el primero.</p>
      )}

      {proyectos !== null && proyectos.length > 0 && (
        <ul className="lista">
          {proyectos.map((proyecto) => (
            <li key={proyecto.id}>
              <Link href={`/proyectos/${proyecto.id}`}>{proyecto.nombre}</Link>
              <span className="texto-secundario"> · creado el {formatearFecha(proyecto.creado)}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function mensajeDe(error: unknown): string {
  return error instanceof Error ? error.message : "Error inesperado.";
}
