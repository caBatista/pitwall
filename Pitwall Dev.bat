@echo off
rem Pitwall from the code, with the sim open: nothing to build, nothing to close.
rem Save a file and the app picks it up by itself (see pitwall\dev.py). Same settings as the installed app.
rem   "Pitwall Dev.bat"          iRacing
rem   "Pitwall Dev.bat" --mock   simulator
setlocal
cd /d "%~dp0"
rem both would write the same files and touch the same pit menu
taskkill /im Pitwall.exe >nul 2>&1
start "" .venv\Scripts\pythonw.exe -m pitwall.desktop --dev %*
