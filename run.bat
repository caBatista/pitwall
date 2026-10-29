@echo off
setlocal
cd /d "%~dp0"

rem Procura um Python real (ignora o atalho da Microsoft Store)
set "PY="
py -3 --version >nul 2>&1 && set "PY=py -3"
if not defined PY (
  python --version >nul 2>&1 && set "PY=python"
)
if not defined PY goto :nopy

if not exist .venv\Scripts\python.exe (
  echo Criando ambiente Python...
  %PY% -m venv .venv || goto :err
  .venv\Scripts\python.exe -m pip install -q -r requirements.txt || goto :err
)
start "" http://localhost:8765
.venv\Scripts\python.exe -m pitwall %*
goto :eof

:nopy
echo.
echo Python nao encontrado. Instale o Python 3.12 em https://www.python.org/downloads/
echo (marque "Add python.exe to PATH") ou rode no PowerShell:
echo     winget install Python.Python.3.12
echo Depois feche esta janela e abra o run.bat de novo.
pause
goto :eof

:err
echo.
echo Falhou ao preparar o ambiente. Veja a mensagem acima.
pause
