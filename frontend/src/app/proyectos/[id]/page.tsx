import { notFound } from "next/navigation";

import { Cabecera } from "@/components/Cabecera";
import { PanelVideos } from "@/components/videos/PanelVideos";

type Props = {
  params: Promise<{ id: string }>;
};

export default async function PaginaProyecto({ params }: Props) {
  const { id } = await params;
  const proyectoId = Number(id);
  if (!/^[1-9]\d{0,9}$/.test(id) || !Number.isSafeInteger(proyectoId)) {
    notFound();
  }

  return (
    <>
      <Cabecera />
      <main className="contenedor">
        <PanelVideos proyectoId={proyectoId} />
      </main>
    </>
  );
}
