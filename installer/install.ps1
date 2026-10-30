# Pitwall per-user installer (no admin, no extra tools).
#   powershell -ExecutionPolicy Bypass -File installer\install.ps1            install / update
#   powershell -ExecutionPolicy Bypass -File installer\install.ps1 -Uninstall remove
# Copies dist\Pitwall to %LOCALAPPDATA%\Programs\Pitwall, adds a Start menu shortcut and an
# entry in Settings > Apps (with uninstall). User data (%LOCALAPPDATA%\Pitwall) is kept.
param([switch]$Uninstall)
$ErrorActionPreference = 'Stop'

$app     = 'Pitwall'
$dest    = Join-Path $env:LOCALAPPDATA "Programs\$app"
$menu    = Join-Path ([Environment]::GetFolderPath('Programs')) "$app.lnk"
$regKey  = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\$app"
$src     = Join-Path (Split-Path $PSScriptRoot -Parent) "dist\$app"

Get-Process -Name $app -ErrorAction SilentlyContinue | Stop-Process -Force -PassThru | Wait-Process -Timeout 10 -ErrorAction SilentlyContinue   # can't overwrite a running exe: wait until it is gone

if ($Uninstall) {
    Remove-Item $menu -ErrorAction SilentlyContinue
    Remove-Item $regKey -Recurse -ErrorAction SilentlyContinue
    Remove-Item $dest -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "$app removed (your maps and settings in $env:LOCALAPPDATA\$app were kept)."
    return
}

if (-not (Test-Path "$src\$app.exe")) { throw "Build first: $src\$app.exe not found (run build.bat)." }

# copy the app (fresh folder, so files removed from a build don't linger)
if (Test-Path $dest) { Remove-Item $dest -Recurse -Force }
New-Item -ItemType Directory -Force $dest | Out-Null
Copy-Item "$src\*" $dest -Recurse -Force
Copy-Item $PSCommandPath (Join-Path $dest 'uninstall.ps1') -Force   # this script doubles as the uninstaller

# Start menu shortcut
$sh = (New-Object -ComObject WScript.Shell).CreateShortcut($menu)
$sh.TargetPath = Join-Path $dest "$app.exe"
$sh.WorkingDirectory = $dest
$sh.IconLocation = Join-Path $dest "$app.exe"
$sh.Description = 'Pitwall - real-time timing for iRacing'
$sh.Save()

# Settings > Apps entry (per user)
$uninstallCmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$dest\uninstall.ps1`" -Uninstall"
New-Item -Path $regKey -Force | Out-Null
$props = @{
    DisplayName = $app; DisplayIcon = (Join-Path $dest "$app.exe"); Publisher = 'Caio Batista'
    DisplayVersion = (Get-Item (Join-Path $dest "$app.exe")).VersionInfo.ProductVersion
    InstallLocation = $dest; UninstallString = $uninstallCmd; NoModify = 1; NoRepair = 1
}
foreach ($k in $props.Keys) {
    $v = $props[$k]; if ($null -eq $v) { $v = '' }   # Windows PowerShell 5.1: no ?? operator
    New-ItemProperty -Path $regKey -Name $k -Value $v -Force | Out-Null
}

Write-Host "$app installed to $dest"
Write-Host "Start menu: $menu"
