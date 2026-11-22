"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

type Enlace = {
  etiqueta: string;
  href: string | null;
};

/** Secciones futuras aparecen deshabilitadas hasta que su fase se implemente. */
const ENLACES: readonly Enlace[] = [
  { etiqueta: "Inicio", href: "/" },
  { etiqueta: "Proyectos", href: "/proyectos" },
  { etiqueta: "Análisis", href: null },
  { etiqueta: "Exportación", href: null },
];

function LogoClipperAI() {
  return (
    <svg className="logo" viewBox="0 0 32 32" aria-hidden="true" focusable="false">
      <defs>
        <linearGradient id="degradado-logo" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#7c5cff" />
          <stop offset="1" stopColor="#22d3ee" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="8" fill="url(#degradado-logo)" />
      <path d="M12 9.5v13l10-6.5z" fill="#0b0d12" />
    </svg>
  );
}

export function Cabecera() {
  const ruta = usePathname();

  return (
    <header className="cabecera">
      <Link href="/" className="marca">
        <LogoClipperAI />
        <span>ClipperAI</span>
      </Link>
      <nav aria-label="Principal">
        <ul className="navegacion">
          {ENLACES.map((enlace, indice) => {
            if (enlace.href === null) {
              const idTooltip = `proximamente-${indice}`;
              return (
                <li key={enlace.etiqueta}>
                  <span
                    className="proximamente"
                    tabIndex={0}
                    aria-disabled="true"
                    aria-describedby={idTooltip}
                  >
                    {enlace.etiqueta}
                    <span id={idTooltip} role="tooltip" className="globo">
                      Próximamente
                    </span>
                  </span>
                </li>
              );
            }

            const activo =
              enlace.href === "/" ? ruta === "/" : ruta?.startsWith(enlace.href) === true;

            return (
              <li key={enlace.etiqueta}>
                <Link href={enlace.href} aria-current={activo ? "page" : undefined}>
                  {enlace.etiqueta}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
    </header>
  );
}
