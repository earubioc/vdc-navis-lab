# Builds the add-in and installs it for the current user (no administrator rights needed).
# Navisworks loads it from %APPDATA%\Autodesk\Navisworks Manage <version>\Plugins\VdcNavisLab\VdcNavisLab.dll
# (the folder name must equal the DLL name, same layout as other third-party plugins).
# Usage, from any PowerShell window:
#   powershell -ExecutionPolicy Bypass -File .\addin\build-and-install.ps1 [-Version 2026]
# The Autodesk DLLs are copied automatically from C:\Program Files\Autodesk\Navisworks Manage <Version>.
# Close Navisworks first: it keeps the DLL locked while it runs.
param([string]$Version = "2026")
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$refs = Join-Path $root "refs\$Version"
$nwDir = Join-Path $env:ProgramFiles "Autodesk\Navisworks Manage $Version"
$needed = @("Api", "Clash", "ComApi", "Interop.ComApi")
# Copy the Autodesk assemblies from the installed Navisworks (they are never committed to git).
if (Test-Path $nwDir) {
    New-Item -ItemType Directory -Force $refs | Out-Null
    foreach ($n in $needed) {
        $src = Join-Path $nwDir "Autodesk.Navisworks.$n.dll"
        if (Test-Path $src) { Copy-Item $src $refs -Force }
    }
}
$missing = @($needed | Where-Object { -not (Test-Path (Join-Path $refs "Autodesk.Navisworks.$_.dll")) })
if ($missing.Count -gt 0) {
    throw ("Missing in {0}: Autodesk.Navisworks.{1}.dll. Navisworks Manage {2} was expected in '{3}'. Install it there, or copy the Autodesk.Navisworks.*.dll files to the refs folder by hand." -f $refs, ($missing -join ".dll, Autodesk.Navisworks."), $Version, $nwDir)
}
if (Get-Process -Name Roamer -ErrorAction SilentlyContinue) {
    throw "Navisworks is running. Close it and run this script again."
}
Write-Host "1/3 Building..."
dotnet build (Join-Path $root "VdcNavisLab.Addin") -c Release --no-incremental -p:NavisworksDir="$refs" --nologo -v minimal
if ($LASTEXITCODE -ne 0) { throw "Build failed (see messages above)." }
$dll = Join-Path $root "VdcNavisLab.Addin\bin\Release\net48\VdcNavisLab.dll"
if (-not (Test-Path $dll)) { throw "Build finished but $dll does not exist." }
Write-Host "2/3 Installing for the current user..."
$old = Join-Path $env:APPDATA "Autodesk\ApplicationPlugins\VdcNavisLab.bundle"
if (Test-Path $old) { Remove-Item $old -Recurse -Force; Write-Host "    removed the earlier bundle install: $old" }
$dest = Join-Path $env:APPDATA "Autodesk\Navisworks Manage $Version\Plugins\VdcNavisLab"
New-Item -ItemType Directory -Force $dest | Out-Null
Copy-Item $dll $dest -Force
Write-Host "3/3 Done. Installed in: $dest"
Get-ChildItem $dest -File | Select-Object FullName, Length | Format-Table -AutoSize
Write-Host "Next: open Navisworks Manage $Version with a model, then run addin\check.ps1"
