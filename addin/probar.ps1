# Prueba completa contra Navisworks real. Un solo comando; espera a que abras Navisworks.
#   powershell -ExecutionPolicy Bypass -File D:\IA_WORK\MCP_NAVIS\addin\probar.ps1
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$cli = Join-Path $root ".venv\Scripts\vdc-navis-lab-cli.exe"
if (-not (Test-Path $cli)) { throw "No existe $cli. Activa el entorno e instala: pip install -e `".[dev]`"" }
Write-Host "Esperando a Navisworks con el add-in cargado (hasta 3 minutos). Abre Navisworks Manage 2026 y un modelo."
$ok = $false
for ($i = 0; $i -lt 90; $i++) {
    $pipes = [IO.Directory]::GetFiles("\\.\pipe\") | Where-Object { $_ -like "*vdc-navis-lab*" }
    if ($pipes) { $ok = $true; break }
    Start-Sleep -Seconds 2
}
if (-not $ok) { Write-Host "NO apareció el pipe. Navisworks no cargó el add-in."; Get-Content (Join-Path $env:LOCALAPPDATA "vdc-navis-lab\addin.log") -Tail 10 -ErrorAction SilentlyContinue; return }
Write-Host "Pipe encontrado: $pipes"
Start-Sleep -Seconds 3
foreach ($step in @(@("nw_status"), @("nw_status"), @("nw_document"), @("nw_analyze"))) {
    Write-Host ""
    Write-Host "=== vdc-navis-lab-cli call $($step -join ' ') ==="
    & $cli call @step
}
Write-Host ""
Write-Host "=== Log del add-in ==="
Get-Content (Join-Path $env:LOCALAPPDATA "vdc-navis-lab\addin.log") -Tail 8
