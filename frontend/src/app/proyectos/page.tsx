import { Cabecera } from "@/components/Cabecera";
import { PanelProyectos } from "@/components/proyectos/PanelProyectos";

export default function PaginaProyectos() {
  return (
    <>
      <Cabecera />
      <main className="contenedor">
        <PanelProyectos />
      </main>
    </>
  );
}
