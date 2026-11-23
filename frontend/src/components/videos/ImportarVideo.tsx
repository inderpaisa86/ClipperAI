"use client";

import { useState, type FormEvent } from "react";

import { importarVideo, seleccionarArchivo } from "@/lib/api/videos";
import type { OrigenVideo, Video } from "@/lib/api/tipos";

type Props = {
  proyectoId: number;
  onImportado: (video: Video) => void;
  onError: (mensaje: string) => void;
};

export function ImportarVideo({ proyectoId, onImportado, onError }: Props) {
  const [ruta, setRuta] = useState("");
  const [ocupado, setOcupado] = useState<null | "seleccion" | "importando">(null);

  async function importar(origen: OrigenVideo) {
    setOcupado("importando");
    try {
      const video = await importarVideo(proyectoId, origen);
      onImportado(video);
      setRuta("");
    } catch (err) {
      onError(mensajeDe(err));
    } finally {
      setOcupado(null);
    }
  }

  async function elegirConSelector() {
    onError("");
    setOcupado("seleccion");
    let seleccionId: string | null = null;
    try {
      seleccionId = (await seleccionarArchivo()).seleccion_id;
    } catch (err) {
      onError(mensajeDe(err));
      setOcupado(null);
      return;
    }
    setOcupado(null);
    if (seleccionId !== null) {
      await importar({ seleccion_id: seleccionId });
    }
  }

  function enviarRuta(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    onError("");
    void importar({ ruta });
  }

  return (
    <div className="importar">
      <div className="fila-acciones">
        <button
          className="boton"
          type="button"
          onClick={elegirConSelector}
          disabled={ocupado !== null}
        >
          {ocupado === "seleccion" ? "Esperando selección…" : "Seleccionar video…"}
        </button>
        <span className="texto-secundario">
          Se registra la ruta original. El archivo no se copia ni se modifica.
        </span>
      </div>

      <form className="formulario" onSubmit={enviarRuta}>
        <label htmlFor="ruta-video">o escriba la ruta absoluta del archivo</label>
        <div className="fila-acciones">
          <input
            id="ruta-video"
            type="text"
            value={ruta}
            onChange={(e) => setRuta(e.target.value)}
            placeholder="C:\Videos\partida.mp4 o /Users/nombre/Videos/partida.mp4"
            spellCheck={false}
          />
          <button
            className="boton secundario"
            type="submit"
            disabled={ocupado !== null || ruta.trim() === ""}
          >
            {ocupado === "importando" ? "Importando…" : "Importar ruta"}
          </button>
        </div>
      </form>
    </div>
  );
}

function mensajeDe(error: unknown): string {
  return error instanceof Error ? error.message : "Error inesperado.";
}
