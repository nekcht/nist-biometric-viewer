; Nist Biometric Viewer / ForensicPrintComparator per-user Windows installer.
; Config, logs, and history are intentionally stored under {userappdata} and preserved.
; The installer never installs biometric/evidence payloads or stores them under {app}.

#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif

#define AppName "Nist Biometric Viewer"
#define AppPublisher "Hellenic Police"
#define AppExeName "ForensicPrintComparator.exe"
#define InstallDirectoryName "ForensicPrintComparator"
#define AppDataName "nistBiometricViewer"
#define SourceRoot ".."

[Setup]
AppId={{95E0F521-2618-4C2D-B035-52EC5D208D80}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={localappdata}\Programs\{#InstallDirectoryName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=output
OutputBaseFilename=NistBiometricViewer_Setup_{#AppVersion}
SetupIconFile={#SourceRoot}\resources\nist_comparator.ico
UninstallDisplayIcon={app}\{#AppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupLogging=yes

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked

[Files]
Source: "{#SourceRoot}\dist\ForensicPrintComparator\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Baseline configuration is copied only for a new user and is preserved on upgrade/uninstall.
Source: "default_user_files\config\settings.ini"; DestDir: "{userappdata}\{#AppDataName}\config"; Flags: onlyifdoesntexist uninsneveruninstall

[Dirs]
; These per-user directories contain no installer-provided biometric/evidence files.
Name: "{userappdata}\{#AppDataName}"; Flags: uninsneveruninstall
Name: "{userappdata}\{#AppDataName}\config"; Flags: uninsneveruninstall
Name: "{userappdata}\{#AppDataName}\logs"; Flags: uninsneveruninstall
Name: "{userappdata}\{#AppDataName}\history"; Flags: uninsneveruninstall
Name: "{userappdata}\{#AppDataName}\exports"; Flags: uninsneveruninstall
Name: "{userappdata}\{#AppDataName}\temp"; Flags: uninsneveruninstall

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent
