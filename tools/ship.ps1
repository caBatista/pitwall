<#
"Fechar as alteracoes": tests, commit, push, build, install, reopen. Everything Caio asks at the end of a change.

  powershell -NoProfile -ExecutionPolicy Bypass -File tools\ship.ps1 -Message "Titulo`n`nCorpo"
  -NoPush     commit only
  -NoBuild    stop after the commit (and push)
  -Dev        reopen as dev mode instead of the EXE

Stops on failing tests. Never closes or opens a window with the driver in the car: then it builds and says so.
Opens through explorer.exe so the app is outside the Claude desktop container and uses the real %LOCALAPPDATA%.
#>
param([Parameter(Mandatory = $true)][string]$Message, [switch]$NoPush, [switch]$NoBuild, [switch]$Dev)
$ErrorActionPreference = 'Continue'
Set-Location (Split-Path $PSScriptRoot)
$py = '.venv\Scripts\python.exe'

& $py -m pytest -q | Select-Object -Last 1
if ($LASTEXITCODE) { 'TESTS FAILED: nothing committed'; exit 1 }
$js = node --test (Get-ChildItem tests\js\*.mjs | ForEach-Object FullName) 2>&1 | Select-String '^. (pass|fail) '
$js
if ($js -match 'fail [1-9]') { 'JS TESTS FAILED: nothing committed'; exit 1 }

git add -A
if (git diff --cached --quiet) { 'nothing to commit' } else {
  git commit -q -m "$Message`n`nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
  git log --oneline -1
}
if (-not $NoPush) { git push -q origin develop; git status -sb | Select-Object -First 1 }
if ($NoBuild) { exit 0 }

cmd /c ".\build.bat" *>&1 | Select-Object -Last 1
& $py tools\simstate.py
if ($LASTEXITCODE -eq 2) { 'IN THE CAR: built, not installed. Run again with -NoPush once out of the car.'; exit 0 }
$sim = (& $py tools\simstate.py) -match 'sim=True'

Get-Process Pitwall -ErrorAction SilentlyContinue | Stop-Process -Force
Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'" | Where-Object { $_.CommandLine -match 'pitwall' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
Start-Sleep 2
powershell -NoProfile -ExecutionPolicy Bypass -File installer\install.ps1 | Select-Object -First 1
$exe = "$env:LOCALAPPDATA\Programs\Pitwall\Pitwall.exe"
"installed $((Get-Item $exe).LastWriteTime.ToString('HH:mm'))"
if (-not $sim -and -not $Dev) { 'iRacing closed: not reopened'; exit 0 }
if ($Dev) { Start-Process explorer.exe -ArgumentList "`"$PWD\Pitwall Dev.bat`"" } else { Start-Process explorer.exe -ArgumentList "`"$exe`"" }
Start-Sleep 6
& $py tools\prefs.py simFull
