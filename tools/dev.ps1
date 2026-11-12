<#
Dev mode on the sim: closes the EXE and opens "Pitwall Dev.bat" through explorer.exe (real %LOCALAPPDATA%).
Refuses with the driver in the car. Saving a .py restarts the server (and zeroes laps and fuel); saving web/ reloads.

  powershell -NoProfile -ExecutionPolicy Bypass -File tools\dev.ps1
#>
Set-Location (Split-Path $PSScriptRoot)
& .venv\Scripts\python.exe tools\simstate.py
if ($LASTEXITCODE -eq 2) { 'IN THE CAR: not opening anything'; exit 2 }
Get-Process Pitwall -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep 1
Start-Process explorer.exe -ArgumentList "`"$PWD\Pitwall Dev.bat`""
Start-Sleep 7
& .venv\Scripts\python.exe tools\prefs.py simFull
