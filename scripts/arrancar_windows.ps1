# Arranca el backend y el frontend de ClipperAI en Windows.
# El backend corre en segundo plano y se detiene cuando termina el frontend.
$ErrorActionPreference = 'Stop'
$raiz = Split-Path -Parent $PSScriptRoot
$directorioBackend = Join-Path $raiz 'backend'
$directorioFrontend = Join-Path $raiz 'frontend'
$python = Join-Path $directorioBackend '.venv\Scripts\python.exe'

if (-not (Test-Path $python)) {
    throw 'Falta el entorno del backend. Ejecute "uv sync" dentro de la carpeta backend.'
}

$backend = Start-Process -FilePath $python `
    -ArgumentList '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000' `
    -WorkingDirectory $directorioBackend -PassThru -NoNewWindow

try {
    Set-Location -Path $directorioFrontend
    npm run dev
}
finally {
    if (-not $backend.HasExited) {
        Stop-Process -Id $backend.Id -Force
    }
}
