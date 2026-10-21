# Un solo comando: espera a que cierres Navisworks, compila, instala, espera a que lo abras y prueba todo.
#   powershell -ExecutionPolicy Bypass -File D:\IA_WORK\MCP_NAVIS\addin\todo.ps1
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
while (Get-Process -Name Roamer -ErrorAction SilentlyContinue) {
    Write-Host "Cierra Navisworks para continuar (el script espera)..."
    Start-Sleep -Seconds 4
}
& (Join-Path $here "build-and-install.ps1")
Write-Host ""
Write-Host ">>> Ahora abre Navisworks Manage 2026 y tu modelo. El script lo espera."
& (Join-Path $here "probar.ps1")
