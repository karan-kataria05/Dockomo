; Dockomo.iss -- Inno Setup script.
; Installs the full onedir PyInstaller build (dist\Dockomo\), including the
; bundled vina.exe, so the end user needs nothing pre-installed.
;
; Build with Inno Setup after running PyInstaller:
;   pyinstaller Dockomo.spec
;   iscc Dockomo.iss

#define MyAppName "Dockomo"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Karan Kataria"
#define MyAppExeName "Dockomo.exe"

[Setup]
; Generate your own GUID (Inno Setup > Tools > Generate GUID) and paste it
; here once, then never change it -- it's what lets future updates upgrade
; in place instead of installing side-by-side.
AppId={{6E3D8406-336F-4CF1-87B4-8A73B2BE01C6}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
OutputBaseFilename=DockomoSetup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=assets\icon.ico
DisableProgramGroupPage=yes
; RDKit/Qt/WebEngine bundles are large -- a 64-bit-only install keeps things simple.
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"

[Files]
; Everything PyInstaller produced in onedir mode: Dockomo.exe, all bundled
; libraries, RDKit/Meeko data files, Qt/WebEngine resources, and vina\vina.exe.
Source: "dist\Dockomo\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
