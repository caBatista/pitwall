@echo off
rem Pitwall desktop app: opens its own window (no browser, no port).
rem   Pitwall.bat           iRacing
rem   Pitwall.bat --mock    simulator, to try it without iRacing
setlocal
cd /d "%~dp0"

if not exist .venv\Scripts\pythonw.exe (
  set "PY="
  py -3 --version >nul 2>&1 && set "PY=py -3"
  if not defined PY python --version >nul 2>&1 && set "PY=python"
  if not defined PY (
    echo Python nao encontrado. Instale o Python 3.12: winget install Python.Python.3.12
    pause
    goto :eof
  )
  echo Criando ambiente Python...
  %PY% -m venv .venv
)
rem make sure the app dependencies (pywebview included) are there; quick when already installed
.venv\Scripts\python.exe -m pip install -q -r requirements.txt
start "" .venv\Scripts\pythonw.exe -m pitwall.desktop %*
