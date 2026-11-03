# VDC Navis Lab: one-command installer for Windows (current user, no administrator rights).
# Instalador de un solo comando para Windows (usuario actual, sin permisos de administrador).
#
#   powershell -ExecutionPolicy Bypass -File .\instalar.ps1
#   powershell -ExecutionPolicy Bypass -File .\instalar.ps1 -Navisworks 2025
#
# What it does / Que hace:
#   1. finds Python 3.11+, creates .venv and installs the package
#   2. runs the offline demo
#   3. registers the server in Claude Desktop (read-only unless -AllowWrites)
#   4. for each Navisworks Manage found: copies its DLLs, builds and installs the add-in
# Everything is written to instalacion.log (send it if something fails).
param(
    [string]$Navisworks = "",
    [switch]$AllowWrites,
    [switch]$SkipNavisworks
)
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root
$script:es = (Get-Culture).Name -like "es*"
function T($es, $en) { if ($script:es) { $es } else { $en } }
function Step($n, $txt) { Write-Host ""; Write-Host ("=== {0}. {1}" -f $n, $txt) -ForegroundColor Cyan }
function Fail($es, $en) {
    Write-Host ""
    Write-Host ("ERROR: " + (T $es $en)) -ForegroundColor Red
    Write-Host (T "Detalle en: $root\instalacion.log. Envia ese archivo a quien te dio el programa." "Details in: $root\instalacion.log. Send that file to whoever gave you the program.") -ForegroundColor Yellow
    try { Stop-Transcript | Out-Null } catch { }
    exit 1
}
try { Start-Transcript -Path (Join-Path $root "instalacion.log") -Force | Out-Null } catch { }

# ---------------------------------------------------------------- 1. Python
Step 1 (T "Python y paquete" "Python and package")
function Test-Py($exe, $pre) {
    $ErrorActionPreference = "Continue"
    try { $v = & $exe @pre -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null } catch { return $null }
    if ($LASTEXITCODE -ne 0 -or -not $v) { return $null }
    $parts = ("$v").Trim().Split(".")
    if ($parts.Count -ge 2 -and $parts[0] -eq "3" -and [int]$parts[1] -ge 11) { return ("$v").Trim() }
    return $null
}
$pyExe = $null; $pyPre = @()
foreach ($c in @(@("py", @("-3.13")), @("py", @("-3.12")), @("py", @("-3.11")), @("python", @()), @("python3", @()))) {
    $ver = Test-Py $c[0] $c[1]
    if ($ver) { $pyExe = $c[0]; $pyPre = $c[1]; Write-Host ("Python $ver ({0})" -f $c[0]); break }
}
if (-not $pyExe) {
    Fail "No se encontro Python 3.11 o superior. Instalalo desde https://www.python.org/downloads/ marcando 'Add python.exe to PATH', cierra esta ventana, abre otra y repite." "Python 3.11 or newer was not found. Install it from https://www.python.org/downloads/ ticking 'Add python.exe to PATH', close this window, open a new one and run this again."
}
$venvPy = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    Write-Host (T "Creando el entorno .venv ..." "Creating the .venv environment ...")
    & $pyExe @pyPre -m venv (Join-Path $root ".venv")
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $venvPy)) { Fail "No se pudo crear .venv." "Could not create .venv." }
}
Write-Host (T "Instalando vdc-navis-lab (necesita internet, puede tardar unos minutos) ..." "Installing vdc-navis-lab (needs internet, may take a few minutes) ...")
& $venvPy -m pip install --disable-pip-version-check -e ".[dev]"
if ($LASTEXITCODE -ne 0) { Fail "pip no pudo instalar el paquete." "pip could not install the package." }
$cli = Join-Path $root ".venv\Scripts\vdc-navis-lab-cli.exe"
if (-not (Test-Path $cli)) { Fail "No existe $cli despues de instalar." "$cli does not exist after installing." }

# ---------------------------------------------------------------- 2. Demo
Step 2 (T "Prueba sin Navisworks (demo)" "Offline test (demo)")
$env:PYTHONIOENCODING = "utf-8"; $env:PYTHONUTF8 = "1"
& $cli demo
if ($LASTEXITCODE -ne 0) { Fail "La demo fallo." "The demo failed." }

# ---------------------------------------------------------------- 3. Claude Desktop
Step 3 (T "Registrar en Claude Desktop" "Register in Claude Desktop")
$cfgArgs = @("desktop-config", "--write")
if ($AllowWrites) { $cfgArgs += "--allow-writes" }
& $cli @cfgArgs
if ($LASTEXITCODE -ne 0) {
    Write-Host (T "AVISO: no se pudo registrar en Claude Desktop (revisa el mensaje de arriba). Lo demas sigue." "WARNING: could not register in Claude Desktop (see the message above). Continuing.") -ForegroundColor Yellow
}

# ---------------------------------------------------------------- 4. Navisworks
if ($SkipNavisworks) {
    Write-Host (T "Se omite Navisworks (-SkipNavisworks)." "Skipping Navisworks (-SkipNavisworks).")
} else {
    Step 4 (T "Add-in de Navisworks" "Navisworks add-in")
    $versions = @()
    if ($Navisworks) { $versions = @($Navisworks) }
    else {
        $found = Get-ChildItem (Join-Path $env:ProgramFiles "Autodesk") -Directory -Filter "Navisworks Manage *" -ErrorAction SilentlyContinue
        foreach ($d in $found) { if ($d.Name -match "(\d{4})$") { $versions += $Matches[1] } }
    }
    if ($versions.Count -eq 0) {
        Write-Host (T "No se encontro Navisworks Manage en C:\Program Files\Autodesk. Se instalo solo la parte de Python (sirve con archivos exportados y con la demo)." "Navisworks Manage was not found in C:\Program Files\Autodesk. Only the Python side was installed (it works with exported files and the demo).") -ForegroundColor Yellow
    } elseif (-not (Get-Command dotnet -ErrorAction SilentlyContinue)) {
        Write-Host (T "Falta el SDK de .NET 8 para compilar el add-in. Instalalo con: winget install Microsoft.DotNet.SDK.8   (o desde https://dotnet.microsoft.com/download), cierra esta ventana y repite." "The .NET 8 SDK is needed to build the add-in. Install it with: winget install Microsoft.DotNet.SDK.8   (or from https://dotnet.microsoft.com/download), close this window and run this again.") -ForegroundColor Yellow
    } else {
        Write-Host ((T "Versiones de Navisworks Manage: " "Navisworks Manage versions: ") + ($versions -join ", "))
        if (Get-Process -Name Roamer -ErrorAction SilentlyContinue) {
            Write-Host (T "Cierra Navisworks para continuar (el script espera)..." "Close Navisworks to continue (the script waits)...") -ForegroundColor Yellow
            while (Get-Process -Name Roamer -ErrorAction SilentlyContinue) { Start-Sleep -Seconds 3 }
        }
        $okVersions = @()
        foreach ($v in $versions) {
            Write-Host ""
            Write-Host ((T "--- Navisworks Manage " "--- Navisworks Manage ") + $v) -ForegroundColor Cyan
            try {
                & (Join-Path $root "addin\build-and-install.ps1") -Version $v
                $okVersions += $v
            } catch {
                Write-Host ("ERROR " + $v + ": " + $_.Exception.Message) -ForegroundColor Red
            }
        }
        if ($okVersions.Count -eq 0) {
            Fail "El add-in no se pudo compilar/instalar en ninguna version de Navisworks (ver mensajes arriba)." "The add-in could not be built/installed for any Navisworks version (see messages above)."
        }
        Write-Host ""
        Write-Host (T "Add-in instalado para: " "Add-in installed for: ") -NoNewline
        Write-Host ($okVersions -join ", ") -ForegroundColor Green
    }
}

# ---------------------------------------------------------------- Final
Write-Host ""
Write-Host "================================================================" -ForegroundColor Green
Write-Host (T "LISTO. Siguiente:" "DONE. Next:") -ForegroundColor Green
Write-Host (T "  1. Cierra Claude Desktop por completo (icono junto al reloj, clic derecho, Salir) y abrelo otra vez." "  1. Fully quit Claude Desktop (icon next to the clock, right click, Quit) and open it again.")
Write-Host (T "  2. Abre Navisworks Manage con un modelo (.nwd o .nwf)." "  2. Open Navisworks Manage with a model (.nwd or .nwf).")
Write-Host (T "  3. En Claude escribe: 'Revisa el estado de Navisworks'." "  3. In Claude type: 'Check the status of Navisworks'.")
Write-Host (T "  Si algo no responde: addin\check.ps1 (con Navisworks abierto) y envia instalacion.log." "  If nothing answers: addin\check.ps1 (with Navisworks open) and send instalacion.log.")
Write-Host "================================================================" -ForegroundColor Green
try { Stop-Transcript | Out-Null } catch { }
