; Inno Setup script for Import2Flex.
; Build:  ISCC.exe /DMyAppVersion=1.0.0 installer\Import2Flex.iss
; Expects the PyInstaller one-folder build in dist\Import2Flex and build\icon.ico.

#ifndef MyAppVersion
  #define MyAppVersion "1.0.0"
#endif
#define MyAppName "Import2Flex"
#define MyAppExe "Import2Flex.exe"
#define MyAppURL "https://github.com/mrrobotto512/import2flex"

[Setup]
AppId={{8F3C2A51-6B7D-4E2A-9C1F-2D5E7A9B4C10}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppName}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases
VersionInfoVersion={#MyAppVersion}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
; Installs for the current user without admin rights; the user can choose "all users".
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist
OutputBaseFilename=Import2Flex-Setup-{#MyAppVersion}
SetupIconFile=..\build\icon.ico
UninstallDisplayIcon={app}\{#MyAppExe}
UninstallDisplayName={#MyAppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
; The app holds this mutex while running, so setup/uninstall can ask to close it.
AppMutex=Import2FlexRunning
CloseApplications=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "startup"; Description: "Start {#MyAppName} when I sign in to Windows (recommended)"; GroupDescription: "Startup:"
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\Import2Flex\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion

[InstallDelete]
; Remove files left by an older version's bundled libraries.
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#MyAppName}"; ValueData: """{app}\{#MyAppExe}"" --minimized"; Tasks: startup; Flags: uninsdeletevalue

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
Filename: "https://www.makemkv.com/download/"; Description: "Download MakeMKV (required for ripping - not found on this PC)"; Flags: shellexec postinstall skipifsilent nowait; Check: not MakeMKVInstalled

[Code]
function MakeMKVInstalled: Boolean;
begin
  Result := FileExists(ExpandConstant('{commonpf32}\MakeMKV\makemkvcon64.exe')) or
            FileExists(ExpandConstant('{commonpf64}\MakeMKV\makemkvcon64.exe'));
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  { The app can also add itself to startup from Settings - always clean that up. }
  if CurUninstallStep = usPostUninstall then
    RegDeleteValue(HKEY_CURRENT_USER, 'Software\Microsoft\Windows\CurrentVersion\Run', '{#MyAppName}');
end;
