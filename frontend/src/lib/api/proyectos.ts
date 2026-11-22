import { solicitarApi } from "./cliente";
import type { Proyecto } from "./tipos";

export function listarProyectos(): Promise<Proyecto[]> {
  return solicitarApi<Proyecto[]>("proyectos");
}

export function crearProyecto(nombre: string): Promise<Proyecto> {
  return solicitarApi<Proyecto>("proyectos", { metodo: "POST", cuerpo: { nombre } });
}
