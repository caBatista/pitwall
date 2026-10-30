; Inno Setup script: one-file Pitwall-Setup.exe for distribution (per user, no admin).
;   "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\pitwall.iss
; Builds from dist\Pitwall (run build.bat first). Output: dist\Pitwall-Setup.exe

#define AppName "Pitwall"
#define AppVersion "0.1.0"

[Setup]
AppId={{6B2C1E4A-9F1D-4C7E-B3B5-8C2E7A51D0F4}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Caio Batista
AppPublisherURL=https://caiobatista.dev
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=Pitwall-Setup
SetupIconFile=..\build-assets\pitwall.ico
UninstallDisplayIcon={app}\Pitwall.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Files]
Source: "..\dist\Pitwall\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\{#AppName}"; Filename: "{app}\Pitwall.exe"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\Pitwall.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Run]
Filename: "{app}\Pitwall.exe"; Description: "Open Pitwall"; Flags: nowait postinstall skipifsilent
