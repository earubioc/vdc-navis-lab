<#
  Instala el add-in de VDC Navis Lab para cada Navisworks Manage que haya en este equipo y deja la licencia de prueba.
  Ejecutar con PowerShell como administrador, con el mismo usuario que usara Claude:
    powershell -ExecutionPolicy Bypass -File .\instalar-prueba.ps1
    powershell -ExecutionPolicy Bypass -File .\instalar-prueba.ps1 -Anios 2025,2026 -SinMcpb
  Cierre Navisworks antes. Para quitar todo: desinstalar-prueba.ps1.
#>
param(
    [int[]]$Anios = @(),
    [switch]$SinMcpb
)
$ErrorActionPreference = 'Stop'
$aqui = $PSScriptRoot
if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole('Administrator')) {
    Write-Host 'FALLA: abra PowerShell como administrador (el MSI instala por equipo).'; exit 1
}
if (Get-Process Roamer -ErrorAction SilentlyContinue) { Write-Host 'FALLA: cierre Navisworks y repita.'; exit 1 }
if ($Anios.Count -eq 0) {
    $Anios = @(Get-ChildItem 'C:\Program Files\Autodesk' -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '^Navisworks Manage (\d{4})$' } | ForEach-Object { [int]$Matches[1] })
}
if ($Anios.Count -eq 0) { Write-Host 'FALLA: no hay Navisworks Manage en este equipo. Use -Anios 2025 (o 2026) para instalar igual.'; exit 1 }
$fallos = 0
foreach ($y in $Anios) {
    $msi = Get-ChildItem -Path (Join-Path $aqui 'msi') -Filter "VdcNavisLab-$y-*.msi" -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $msi) { Write-Host "OMITIDO  Navisworks $y : esta carpeta no trae MSI para ese anio."; continue }
    $log = Join-Path $env:TEMP "vdc-navis-lab-msi-$y.log"
    $p = Start-Process msiexec.exe -ArgumentList @('/i', "`"$($msi.FullName)`"", '/qn', '/l*v', "`"$log`"") -Wait -PassThru
    $dll = "C:\Program Files\Autodesk\Navisworks Manage $y\Plugins\VdcNavisLab\VdcNavisLab.dll"
    if (($p.ExitCode -in 0, 3010) -and (Test-Path $dll)) { Write-Host "PASS  Navisworks $y : add-in instalado ($($msi.Name))" }
    else { Write-Host "FAIL  Navisworks $y : msiexec codigo $($p.ExitCode); registro en $log"; $fallos++ }
}
$tok = Join-Path $aqui 'licencia\license.token'
if (Test-Path $tok) {
    $datos = Join-Path $env:USERPROFILE '.vdc_navis_lab'
    New-Item -ItemType Directory -Path $datos -Force | Out-Null
    Copy-Item $tok (Join-Path $datos 'license.token') -Force
    Write-Host 'PASS  licencia de prueba copiada a la carpeta de datos de este usuario'
}
if (-not $SinMcpb) {
    $mcpb = Get-ChildItem -Path $aqui -Filter 'vdc-navis-lab-*-offline-windows.mcpb' | Select-Object -First 1
    if ($mcpb) { Write-Host 'Abriendo la extension en Claude Desktop: confirme "Instalar" en la ventana que aparece.'; Start-Process $mcpb.FullName }
}
Write-Host ''
if ($fallos -eq 0) { Write-Host 'Listo. Abra Navisworks con una COPIA del modelo y siga con campo.ps1.'; exit 0 } else { Write-Host "$fallos instalacion(es) fallaron."; exit 1 }
