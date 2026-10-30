@echo off
rem Builds dist\Pitwall\Pitwall.exe (one folder, no console). Needs: pip install pyinstaller pillow
cd /d "%~dp0"
.venv\Scripts\pyinstaller --noconfirm --clean --windowed --onedir --name Pitwall ^
  --icon build-assets\pitwall.ico ^
  --add-data "web;web" --add-data "maps\library;maps\library" ^
  --paths . --collect-all webview --hidden-import clr ^
  build-assets\pitwall_app.py
