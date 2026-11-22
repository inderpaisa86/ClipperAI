export function formatearBytes(bytes: number): string {
  const unidades = ["B", "KB", "MB", "GB", "TB"];
  let valor = bytes;
  let indice = 0;
  while (valor >= 1024 && indice < unidades.length - 1) {
    valor /= 1024;
    indice += 1;
  }
  const decimales = indice === 0 ? 0 : 1;
  return `${valor.toLocaleString("es", { maximumFractionDigits: decimales })} ${unidades[indice]}`;
}

export function formatearDuracion(segundos: number | null): string {
  if (segundos === null) {
    return "Desconocida";
  }
  const total = Math.round(segundos);
  const horas = Math.floor(total / 3600);
  const minutos = Math.floor((total % 3600) / 60);
  const resto = total % 60;
  const dosDigitos = (n: number) => n.toString().padStart(2, "0");
  return horas > 0
    ? `${horas}:${dosDigitos(minutos)}:${dosDigitos(resto)}`
    : `${minutos}:${dosDigitos(resto)}`;
}

export function formatearResolucion(ancho: number, alto: number): string {
  return `${ancho} × ${alto}`;
}

export function formatearFps(fps: number | null): string {
  return fps === null ? "Desconocido" : `${fps.toLocaleString("es", { maximumFractionDigits: 2 })} fps`;
}

export function formatearFecha(iso: string): string {
  const fecha = new Date(iso);
  return Number.isNaN(fecha.getTime())
    ? iso
    : fecha.toLocaleString("es", { dateStyle: "medium", timeStyle: "short" });
}
