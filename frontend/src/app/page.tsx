import { Cabecera } from "@/components/Cabecera";
import { EstadoBackend } from "@/components/EstadoBackend";

export default function PaginaInicio() {
  return (
    <>
      <Cabecera />
      <main className="contenedor">
        <section className="bienvenida">
          <h1>ClipperAI</h1>
          <p>
            Analiza videos locales y propone los momentos que valen la pena convertir en clips.
            Todo el procesamiento ocurre en tu equipo.
          </p>
        </section>
        <EstadoBackend />
      </main>
    </>
  );
}
