#!/usr/bin/env bash
# Arranca el backend y el frontend de ClipperAI en macOS (Intel o Apple Silicon).
# Pendiente de prueba: el desarrollo inicial es en Windows.
set -euo pipefail

raiz="$(cd "$(dirname "$0")/.." && pwd)"
python="$raiz/backend/.venv/bin/python"

if [[ ! -x "$python" ]]; then
  echo "Falta el entorno del backend. Ejecute 'uv sync' dentro de la carpeta backend." >&2
  exit 1
fi

(cd "$raiz/backend" && exec "$python" -m uvicorn app.main:app --host 127.0.0.1 --port 8000) &
backend_pid=$!
trap 'kill "$backend_pid" 2>/dev/null || true' EXIT

cd "$raiz/frontend"
npm run dev
