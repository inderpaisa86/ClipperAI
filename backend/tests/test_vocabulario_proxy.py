"""Paridad del vocabulario cerrado de señales entre el backend y el proxy de Next.js."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from app.plugins.contrato import TIPOS_SENAL_PERMITIDOS

RAIZ_REPOSITORIO = Path(__file__).resolve().parents[2]
DESTINOS_TS = RAIZ_REPOSITORIO / "frontend" / "src" / "lib" / "proxy" / "destinos.ts"


def _tipos_en_el_proxy() -> set[str]:
    texto = DESTINOS_TS.read_text(encoding="utf-8")
    coincidencia = re.search(r"TIPOS_SENAL_PERMITIDOS\s*=\s*\[([^\]]*)\]\s*as const", texto)
    assert coincidencia is not None, "destinos.ts debe declarar TIPOS_SENAL_PERMITIDOS ... as const"
    return set(re.findall(r'"([^"]+)"', coincidencia.group(1)))


def test_vocabulario_del_backend_y_del_proxy_son_iguales():
    assert _tipos_en_el_proxy() == set(TIPOS_SENAL_PERMITIDOS)


def test_el_vocabulario_actual_es_el_aprobado():
    assert set(TIPOS_SENAL_PERMITIDOS) == {
        "energia_audio",
        "silencio",
        "cambio_intensidad",
        "cambio_escena",
        "movimiento",
        "brillo",
    }


_SCRIPT = """
import {{ resolverDestino }} from "{ruta}";
const casos = {casos};
const salida = casos.map(([metodo, segmentos, consulta]) => {{
  const r = resolverDestino(metodo, segmentos, new URLSearchParams(consulta));
  return {{ ok: r.ok, estado: r.ok ? 200 : r.estado }};
}});
console.log(JSON.stringify(salida));
"""

_RUTA_SENALES = ["videos", "1", "analisis", "audio", "senales"]


@pytest.mark.skipif(shutil.which("node") is None, reason="Se requiere Node.js para ejecutar el proxy real")
def test_proxy_valida_el_parametro_tipo_con_el_vocabulario_cerrado(tmp_path):
    casos = [
        ["GET", _RUTA_SENALES, "tipo=silencio"],
        ["GET", _RUTA_SENALES, "tipo=energia_audio"],
        ["GET", _RUTA_SENALES, "tipo=cambio_intensidad"],
        ["GET", _RUTA_SENALES, "tipo=cambio_escena"],
        ["GET", _RUTA_SENALES, "tipo=movimiento"],
        ["GET", _RUTA_SENALES, "tipo=brillo"],
        ["GET", _RUTA_SENALES, "tipo=escena"],
        ["GET", _RUTA_SENALES, "tipo=SILENCIO"],
        ["GET", _RUTA_SENALES, "tipo="],
        ["GET", _RUTA_SENALES, "tipo=silencio&tipo=escena"],
        ["GET", _RUTA_SENALES, "limite=10&tipo=silencio"],
    ]
    archivo = tmp_path / "prueba_tipos.mjs"
    archivo.write_text(
        _SCRIPT.format(
            ruta=DESTINOS_TS.as_uri(),
            casos=json.dumps(casos),
        ),
        encoding="utf-8",
    )
    resultado = subprocess.run(
        ["node", str(archivo)], capture_output=True, text=True, timeout=60, check=False
    )
    assert resultado.returncode == 0, resultado.stderr
    obtenidos = json.loads(resultado.stdout.strip().splitlines()[-1])
    esperados = [
        {"ok": True, "estado": 200},
        {"ok": True, "estado": 200},
        {"ok": True, "estado": 200},
        {"ok": True, "estado": 200},
        {"ok": True, "estado": 200},
        {"ok": True, "estado": 200},
        {"ok": False, "estado": 400},
        {"ok": False, "estado": 400},
        {"ok": False, "estado": 400},
        {"ok": False, "estado": 400},
        {"ok": True, "estado": 200},
    ]
    assert obtenidos == esperados


@pytest.mark.skipif(shutil.which("node") is None, reason="Se requiere Node.js para ejecutar el proxy real")
def test_proxy_permite_iniciar_el_analisis_por_post_y_no_por_otros_metodos(tmp_path):
    casos = [
        ["POST", ["videos", "1", "analisis"], ""],
        ["GET", ["videos", "1", "analisis"], ""],
        ["PUT", ["videos", "1", "analisis"], ""],
        ["POST", ["videos", "1", "analisis", "audio"], ""],
    ]
    archivo = tmp_path / "prueba_post.mjs"
    archivo.write_text(
        _SCRIPT.format(ruta=DESTINOS_TS.as_uri(), casos=json.dumps(casos)),
        encoding="utf-8",
    )
    resultado = subprocess.run(
        ["node", str(archivo)], capture_output=True, text=True, timeout=60, check=False
    )
    assert resultado.returncode == 0, resultado.stderr
    obtenidos = json.loads(resultado.stdout.strip().splitlines()[-1])
    assert obtenidos == [
        {"ok": True, "estado": 200},
        {"ok": True, "estado": 200},
        {"ok": False, "estado": 405},
        {"ok": False, "estado": 405},
    ]
