<#
  Prueba de campo de VDC Navis Lab en este equipo: un solo comando.
  Detecta versiones, corre verify (con escrituras solo si se confirma que el modelo abierto es una COPIA), bench --live y
  nw_analyze, y escribe un informe de cifras (JSON y markdown) sin nombres de proyecto, modelo, archivo, prueba ni ruta.

  Uso (con Navisworks abierto y UNA COPIA del modelo cargada):
    powershell -ExecutionPolicy Bypass -File .\campo.ps1 -Equipo E2 -Modelo M2
    powershell -ExecutionPolicy Bypass -File .\campo.ps1 -Equipo E2 -Modelo M2 -SinEscrituras
    powershell -ExecutionPolicy Bypass -File .\campo.ps1 -Equipo E2 -Modelo M2 -ConfirmoCopia   # sin pregunta

  -Equipo y -Modelo son identificadores genericos (E1, E2, M1, M2...), nunca nombres.
  No necesita instalar la extension: usa el paquete .mcpb de esta carpeta y el Python del equipo (3.11 a 3.13).
#>
param(
    [string]$Equipo = 'E1',
    [string]$Modelo = 'M1',
    [switch]$ConfirmoCopia,
    [switch]$SinEscrituras,
    [string]$Out = ''
)
$ErrorActionPreference = 'Stop'
$aqui = $PSScriptRoot
$mcpb = Get-ChildItem -Path $aqui -Filter 'vdc-navis-lab-*-offline-windows.mcpb' | Select-Object -First 1
if (-not $mcpb) { Write-Host 'FALLA: no hay un archivo .mcpb en esta carpeta.'; exit 2 }

# Python 3.11 a 3.13
$py = $null; $pre = @()
foreach ($c in @(@('py', @('-3.13')), @('py', @('-3.12')), @('py', @('-3.11')), @('python', @()))) {
    try {
        $exe = $c[0]; $extra = $c[1]
        $v = & $exe @extra -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
        if ($LASTEXITCODE -eq 0 -and $v -match '^3\.(11|12|13)$') { $py = $c[0]; $pre = $c[1]; break }
    } catch { }
}
if (-not $py) { Write-Host 'FALLA: se necesita Python 3.11, 3.12 o 3.13 (python.org, marcando Add python.exe to PATH).'; exit 2 }

# El paquete se abre una vez en una carpeta temporal; nada se instala ni se descarga.
$dest = Join-Path $env:TEMP 'vdc-navis-lab-campo'
$marca = Join-Path $dest ('.' + $mcpb.Name)
if (-not (Test-Path $marca)) {
    if (Test-Path $dest) { Remove-Item $dest -Recurse -Force }
    $zip = Join-Path $env:TEMP ($mcpb.Name + '.zip')
    Copy-Item $mcpb.FullName $zip -Force
    Expand-Archive -Path $zip -DestinationPath $dest -Force
    Remove-Item $zip -Force
    New-Item -ItemType File -Path $marca -Force | Out-Null
}
$env:PYTHONPATH = Join-Path $dest 'server\lib'
$env:PYTHONUTF8 = '1'
$tok = Join-Path $aqui 'licencia\license.token'
if ((Test-Path $tok) -and -not $env:VDC_NAVIS_LAB_LICENSE_FILE) { $env:VDC_NAVIS_LAB_LICENSE_FILE = $tok }
if (-not $Out) { $Out = Join-Path $aqui 'resultados' }

$a = @('-m', 'vdc_navis_lab.cli', 'field-test', '--equipo', $Equipo, '--modelo', $Modelo, '--out', $Out)
if ($ConfirmoCopia) { $a += '--confirmo-copia' }
if ($SinEscrituras) { $a += '--sin-escrituras' }
& $py @pre @a
exit $LASTEXITCODE
