# Builds the add-in and installs it for the current user (no administrator rights needed).
# Usage, from any PowerShell window:
#   powershell -ExecutionPolicy Bypass -File D:\IA_WORK\MCP_NAVIS\addin\build-and-install.ps1
# Close Navisworks first: it keeps the DLL locked while it runs.
param([string]$Version = "2026")
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$refs = Join-Path $root "refs\$Version"
if (-not (Test-Path (Join-Path $refs "Autodesk.Navisworks.Api.dll"))) {
    throw "Missing $refs\Autodesk.Navisworks.Api.dll. Copy the Autodesk.Navisworks.*.dll files there first."
}
if (Get-Process -Name Roamer -ErrorAction SilentlyContinue) {
    throw "Navisworks is running. Close it and run this script again."
}
Write-Host "1/3 Building..."
dotnet build (Join-Path $root "VdcNavisLab.Addin") -c Release -p:NavisworksDir="$refs" --nologo -v minimal
if ($LASTEXITCODE -ne 0) { throw "Build failed (see messages above)." }
$dll = Join-Path $root "VdcNavisLab.Addin\bin\Release\net48\VdcNavisLab.Addin.dll"
if (-not (Test-Path $dll)) { throw "Build finished but $dll does not exist." }
Write-Host "2/3 Installing for the current user..."
$bundle = Join-Path $env:APPDATA "Autodesk\ApplicationPlugins\VdcNavisLab.bundle"
New-Item -ItemType Directory -Force (Join-Path $bundle "Contents") | Out-Null
Copy-Item (Join-Path $root "bundle\VdcNavisLab.bundle\PackageContents.xml") $bundle -Force
Copy-Item $dll (Join-Path $bundle "Contents") -Force
Write-Host "3/3 Done. Installed in: $bundle"
Get-ChildItem $bundle -Recurse -File | Select-Object FullName, Length | Format-Table -AutoSize
Write-Host "Next: open Navisworks Manage $Version, open a model, then check with: vdc-navis-lab-cli call nw_status"
