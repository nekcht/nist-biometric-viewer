; Nist Biometric Viewer per-user Windows installer.
; Config, logs, and history are intentionally stored under {userappdata} and preserved.
; The installer never installs biometric/evidence payloads or stores them under {app}.

#ifndef AppVersion
  #define AppVersion "1.2.0"
#endif

#define AppName "Nist Biometric Viewer"
#define AppPublisher "Christou Nektarios"
#define AppExeName "NistBiometricViewer.exe"
#define InstallDirectoryName "NistBiometricViewer"
#define AppDataName "NistBiometricViewer"
#define SourceRoot ".."

[Setup]
AppId={{95E0F521-2618-4C2D-B035-52EC5D208D80}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={localappdata}\Programs\{#InstallDirectoryName}
UsePreviousAppDir=no
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
MinVersion=10.0
OutputDir=output
OutputBaseFilename=NistBiometricViewer_Setup_{#AppVersion}
SetupIconFile={#SourceRoot}\resources\nist_biometric_viewer.ico
UninstallDisplayIcon={app}\{#AppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupLogging=yes

[Messages]
WindowsVersionNotSupported=Nist Biometric Viewer requires Windows 10 or newer. Windows 7 is not supported.

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked

[Files]
Source: "{#SourceRoot}\dist\NistBiometricViewer\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

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
