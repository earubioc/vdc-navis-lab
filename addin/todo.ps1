# One command: waits for you to close Navisworks, builds and installs the add-in, waits for you to open it and tests everything.
# Un solo comando: espera a que cierres Navisworks, compila, instala, espera a que lo abras y prueba todo.
#   powershell -ExecutionPolicy Bypass -File .\addin\todo.ps1 [-Version 2026]
param([string]$Version = "")
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $Version) {
    $found = @()
    $dirs = Get-ChildItem (Join-Path $env:ProgramFiles "Autodesk") -Directory -Filter "Navisworks Manage *" -ErrorAction SilentlyContinue
    foreach ($d in $dirs) { if ($d.Name -match "(\d{4})$") { $found += $Matches[1] } }
    if ($found.Count -eq 1) { $Version = $found[0] }
    elseif ($found.Count -gt 1) { $Version = Read-Host ("Versions found: " + ($found -join ", ") + ". Which one do you use now? / Cual usas ahora?") }
    else { $Version = "2026" }
}
while (Get-Process -Name Roamer -ErrorAction SilentlyContinue) {
    Write-Host "Cierra Navisworks para continuar (el script espera)... / Close Navisworks to continue (the script waits)..."
    Start-Sleep -Seconds 4
}
& (Join-Path $here "build-and-install.ps1") -Version $Version
Write-Host ""
Write-Host ">>> Now open Navisworks Manage $Version and your model. The script waits. / Ahora abre Navisworks Manage $Version y tu modelo. El script espera."
& (Join-Path $here "probar.ps1") -Version $Version
