#define MyAppName "Rúnmál"
#ifndef MyAppVersion
  #define MyAppVersion "0.1.0"
#endif
#define MyAppPublisher "Volmarr / Rúnmál"
#define MyAppExeName "Runmal.exe"

[Setup]
AppId={{9F0150A8-60E6-4D20-BA3E-99185C62C9B2}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\Runmal
DefaultGroupName=Rúnmál
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\..\artifacts
OutputBaseFilename=Runmal-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=..\..\build\runmal.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: checkedonce

[Files]
Source: "..\..\dist\Runmal\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Rúnmál"; Filename: "{app}\{#MyAppExeName}"; Parameters: "open"; WorkingDir: "{app}"; Comment: "Open Rúnmál"
Name: "{autoprograms}\Rúnmál Control Center"; Filename: "{app}\{#MyAppExeName}"; Parameters: "control"; WorkingDir: "{app}"; Comment: "Manage the local Rúnmál service"
Name: "{autodesktop}\Rúnmál"; Filename: "{app}\{#MyAppExeName}"; Parameters: "open"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Parameters: "open"; Description: "Launch Rúnmál"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
