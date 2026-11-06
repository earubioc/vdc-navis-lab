<#
  Prueba de instalación limpia en Windows, para el MSI del add-in y para el MCPB del servidor.
  Pensada para Windows Sandbox o una máquina virtual recién creada, con PowerShell como administrador.

  Uso:
    .\probar-instalacion.ps1 -Msi VdcNavisLab-2025-1.0.1.msi -Year 2025
    .\probar-instalacion.ps1 -Msi VdcNavisLab-2025-1.0.1.msi -Year 2025 -MsiNueva VdcNavisLab-2025-1.0.2.msi
    .\probar-instalacion.ps1 -Mcpb vdc-navis-lab-1.0.1.mcpb          # necesita uv (https://docs.astral.sh/uv/)
    .\probar-instalacion.ps1 -Msi ... -Year 2025 -Mcpb ...           # las dos cosas

  Imprime PASS o FAIL por paso y termina con código 0 solo si todo pasó. No imprime nada de ningún modelo.
  No necesita Navisworks: dice si lo encuentra, pero el MSI se instala igual (deja el DLL donde Navisworks lo buscaría).
#>
param(
    [string]$Msi,
    [int]$Year = 2025,
    [string]$MsiNueva,
    [string]$Mcpb,
    [string]$Dll,           # DLL de origen, si se quiere comparar el hash con el instalado
    [switch]$Conservar      # no desinstala al final
)
$ErrorActionPreference = 'Stop'
$script:fallos = 0
function Paso($nombre, [scriptblock]$cuerpo) {
    $t0 = Get-Date
    try { $detalle = & $cuerpo; $ok = $true } catch { $detalle = $_.Exception.Message; $ok = $false; $script:fallos++ }
    '{0}  {1,-44} {2,6:N1} s  {3}' -f ($(if ($ok) { 'PASS' } else { 'FAIL' })), $nombre, ((Get-Date) - $t0).TotalSeconds, $detalle
}
function Exigir($cond, $msg) { if (-not $cond) { throw $msg } }
function Instalar($archivo, $log) {
    $p = Start-Process msiexec.exe -ArgumentList @('/i', "`"$archivo`"", '/qn', '/l*v', "`"$log`"") -Wait -PassThru
    Exigir ($p.ExitCode -in 0, 3010) "msiexec /i terminó con código $($p.ExitCode); registro en $log"
    $p.ExitCode
}

if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole('Administrator')) {
    Write-Host 'FAIL  Ejecute PowerShell como administrador (el MSI instala por equipo).'; exit 1
}

if ($Msi) {
    $Msi = (Resolve-Path $Msi).Path
    $carpeta = "C:\Program Files\Autodesk\Navisworks Manage $Year\Plugins\VdcNavisLab"
    $dllInst = Join-Path $carpeta 'VdcNavisLab.dll'
    $log = Join-Path $env:TEMP 'vdc-navis-lab-msi.log'

    Paso 'Navisworks instalado (informativo)' {
        $exe = "C:\Program Files\Autodesk\Navisworks Manage $Year\Roamer.exe"
        if (Test-Path $exe) { "Navisworks $Year encontrado" } else { "Navisworks $Year no está en este equipo (normal en un equipo limpio de pruebas)" }
    }
    Paso 'instalación por usuario previa (debe no haber)' {
        $u = Join-Path $env:APPDATA "Autodesk\Navisworks Manage $Year\Plugins\VdcNavisLab\VdcNavisLab.dll"
        Exigir (-not (Test-Path $u)) "hay una copia por usuario en $u: Navisworks cargaría el add-in dos veces; bórrela antes"
        'sin copia por usuario'
    }
    Paso 'MSI: instalación silenciosa' { "código $(Instalar $Msi $log)" }
    Paso 'MSI: el DLL quedó donde Navisworks lo busca' {
        Exigir (Test-Path $dllInst) "no existe $dllInst"
        $h = (Get-FileHash $dllInst -Algorithm SHA256).Hash
        if ($Dll) { Exigir ($h -eq (Get-FileHash (Resolve-Path $Dll).Path -Algorithm SHA256).Hash) 'el DLL instalado no coincide con el de origen' }
        "$((Get-Item $dllInst).Length) bytes, sha256 $($h.Substring(0,12))..."
    }
    Paso 'MSI: aparece en Programas instalados' {
        $k = Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*' |
            Where-Object { $_.DisplayName -like "VDC Navis Lab for Navisworks Manage $Year*" }
        Exigir ($null -ne $k) 'no hay entrada de desinstalación'
        "versión $($k.DisplayVersion)"
    }
    Paso 'MSI: reinstalar la misma versión' { "código $(Instalar $Msi $log)"; Exigir (Test-Path $dllInst) 'el DLL desapareció' }
    if ($MsiNueva) {
        $MsiNueva = (Resolve-Path $MsiNueva).Path
        Paso 'MSI: actualizar a la versión nueva' {
            $antes = (Get-FileHash $dllInst).Hash
            Instalar $MsiNueva $log | Out-Null
            Exigir (Test-Path $dllInst) 'el DLL desapareció al actualizar'
            $n = @(Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*' |
                Where-Object { $_.DisplayName -like "VDC Navis Lab for Navisworks Manage $Year*" }).Count
            Exigir ($n -eq 1) "quedaron $n entradas instaladas; debía quedar una"
            if ((Get-FileHash $dllInst).Hash -eq $antes) { 'actualizó (el DLL no cambió: misma compilación)' } else { 'actualizó y el DLL cambió' }
        }
    }
    if (-not $Conservar) {
        Paso 'MSI: desinstalar' {
            $p = Start-Process msiexec.exe -ArgumentList @('/x', "`"$Msi`"", '/qn') -Wait -PassThru
            if ($MsiNueva -and $p.ExitCode -ne 0) { $p = Start-Process msiexec.exe -ArgumentList @('/x', "`"$MsiNueva`"", '/qn') -Wait -PassThru }
            Exigir ($p.ExitCode -in 0, 3010) "msiexec /x terminó con código $($p.ExitCode)"
            Exigir (-not (Test-Path $dllInst)) 'el DLL sigue instalado'
            'DLL retirado'
        }
    }
}

if ($Mcpb) {
    $Mcpb = (Resolve-Path $Mcpb).Path
    $dest = Join-Path $env:TEMP 'vdc-navis-lab-mcpb'
    Paso 'MCPB: uv disponible' {
        $v = (& uv --version) 2>&1
        Exigir ($LASTEXITCODE -eq 0) 'no se encontró uv (Claude Desktop lo trae; en una máquina sin él: winget install astral-sh.uv)'
        "$v"
    }
    Paso 'MCPB: abrir el paquete' {
        if (Test-Path $dest) { Remove-Item $dest -Recurse -Force }
        Copy-Item $Mcpb "$Mcpb.zip" -Force
        Expand-Archive "$Mcpb.zip" -DestinationPath $dest -Force
        Remove-Item "$Mcpb.zip"
        $m = Get-Content (Join-Path $dest 'manifest.json') -Raw | ConvertFrom-Json
        "$($m.name) $($m.version), servidor tipo $($m.server.type)"
    }
    Paso 'MCPB: el servidor arranca y responde (16 herramientas)' {
        $h = Join-Path $PSScriptRoot 'handshake.py'
        Exigir (Test-Path $h) "falta $h (copie la carpeta installer completa)"
        $out = & uv run --no-project --with mcp python $h $dest 16 2>&1 | Out-String
        Exigir ($LASTEXITCODE -eq 0) ("el saludo con el servidor falló:`n" + $out)
        ($out -split "`n" | Where-Object { $_ -match '^PASS' }) -join ' | '
    }
}

''
if ($script:fallos -eq 0) { 'TODO PASA' ; exit 0 } else { "$script:fallos paso(s) fallaron"; exit 1 }
