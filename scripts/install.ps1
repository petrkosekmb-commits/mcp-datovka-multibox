$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
python -m venv (Join-Path $projectRoot '.venv')
if ($LASTEXITCODE -ne 0) { throw 'Vytvoreni prostredi selhalo.' }
$runtimePython = Join-Path $projectRoot '.venv\Scripts\python.exe'
& $runtimePython -m pip install $projectRoot
if ($LASTEXITCODE -ne 0) { throw 'Instalace selhala.' }
& $runtimePython -m mcp_datovka.setup init
if ($LASTEXITCODE -ne 0) { throw 'Inicializace selhala.' }
Write-Host 'Pripraveno. Ucet pridate spustenim scripts\nastavit-ucet.ps1.'
