<#
  Desinstalacion limpia de la prueba de campo: add-in de cada anio, licencia, datos del servidor y archivos temporales.
  Ejecutar con PowerShell como administrador:
    powershell -ExecutionPolicy Bypass -File .\desinstalar-prueba.ps1
    powershell -ExecutionPolicy Bypass -File .\desinstalar-prueba.ps1 -ConservarDatos     # deja los informes y el registro
  La extension de Claude Desktop se quita a mano: Configuracion > Extensiones > VDC Navis Lab > Desinstalar.
#>
param([switch]$ConservarDatos)
$ErrorActionPreference = 'Stop'
$aqui = $PSScriptRoot
if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole('Administrator')) {
    Write-Host 'FALLA: abra PowerShell como administrador.'; exit 1
}
if (Get-Process Roamer -ErrorAction SilentlyContinue) { Write-Host 'FALLA: cierre Navisworks y repita.'; exit 1 }
$fallos = 0
foreach ($msi in Get-ChildItem -Path (Join-Path $aqui 'msi') -Filter 'VdcNavisLab-*.msi' -ErrorAction SilentlyContinue) {
    $y = ($msi.Name -split '-')[1]
    $p = Start-Process msiexec.exe -ArgumentList @('/x', "`"$($msi.FullName)`"", '/qn') -Wait -PassThru
    $dir = "C:\Program Files\Autodesk\Navisworks Manage $y\Plugins\VdcNavisLab"
    if ($p.ExitCode -in 0, 3010, 1605 -and -not (Test-Path $dir)) { Write-Host "PASS  Navisworks $y : add-in retirado" }
    else { Write-Host "FAIL  Navisworks $y : msiexec codigo $($p.ExitCode) o la carpeta sigue en su sitio"; $fallos++ }
}
$quedan = @(Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*' -ErrorAction SilentlyContinue |
    Where-Object { $_.DisplayName -like 'VDC Navis Lab for Navisworks Manage*' })
if ($quedan.Count -eq 0) { Write-Host 'PASS  ya no hay entradas de VDC Navis Lab en Programas instalados' } else { Write-Host "FAIL  quedan $($quedan.Count) entrada(s) en Programas instalados"; $fallos++ }
$datos = Join-Path $env:USERPROFILE '.vdc_navis_lab'
if ($ConservarDatos) {
    Remove-Item (Join-Path $datos 'license.token') -Force -ErrorAction SilentlyContinue
    Write-Host 'PASS  licencia retirada; datos conservados'
} elseif (Test-Path $datos) {
    Remove-Item $datos -Recurse -Force
    Write-Host 'PASS  carpeta de datos del servidor eliminada'
}
Remove-Item (Join-Path $env:TEMP 'vdc-navis-lab-campo') -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path $env:TEMP 'vdc-navis-lab-msi-*.log') -Force -ErrorAction SilentlyContinue
Write-Host ''
if ($fallos -eq 0) { Write-Host 'LIMPIO. Falta solo quitar la extension en Claude Desktop (Configuracion > Extensiones).'; exit 0 } else { Write-Host "$fallos problema(s): revise arriba."; exit 1 }
