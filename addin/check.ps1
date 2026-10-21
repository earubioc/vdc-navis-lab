# Shows why the add-in may not be answering. Run it while Navisworks is open.
#   powershell -ExecutionPolicy Bypass -File D:\IA_WORK\MCP_NAVIS\addin\check.ps1
param([string]$Version = "2026")
$dest = Join-Path $env:APPDATA "Autodesk\Navisworks Manage $Version\Plugins\VdcNavisLab"
Write-Host "--- 1. Navisworks running? ---"
$p = Get-Process -Name Roamer -ErrorAction SilentlyContinue
if ($p) { $p | Select-Object Id, ProcessName, MainWindowTitle | Format-Table -AutoSize } else { Write-Host "NO: Roamer.exe is not running. Open Navisworks Manage $Version." }
Write-Host "--- 2. Installed plugin ---"
if (Test-Path $dest) { Get-ChildItem $dest -File | Select-Object FullName, Length | Format-Table -AutoSize } else { Write-Host "NO: $dest does not exist. Run build-and-install.ps1." }
Write-Host "--- 3. DLL loaded inside Navisworks? ---"
if ($p) { $m = (Get-Process Roamer).Modules | Where-Object { $_.ModuleName -eq "VdcNavisLab.dll" }; if ($m) { $m | Select-Object ModuleName, FileName | Format-List } else { Write-Host "NO: Navisworks has not loaded VdcNavisLab.dll." } }
Write-Host "--- 4. Add-in log ---"
$log = Join-Path $env:LOCALAPPDATA "vdc-navis-lab\addin.log"
if (Test-Path $log) { Get-Content $log -Tail 15 } else { Write-Host "NO LOG: the add-in code never ran (file $log does not exist)." }
Write-Host "--- 5. Named pipes ---"
$pipes = [IO.Directory]::GetFiles("\\.\pipe\") | Where-Object { $_ -like "*vdc-navis-lab*" }
if ($pipes) { $pipes } else { Write-Host "NO pipe named vdc-navis-lab.* exists." }
