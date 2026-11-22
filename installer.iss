; Inno Setup script. Install Inno Setup (free, jrsoftware.org), run build.bat first,
; then open this file in Inno Setup and press Compile (or run build.bat, which does it).
; Output: installer_output\CommandCenter_Setup.exe  (a normal Windows install wizard)

#define AppName "Command Center"
#define AppVersion "1.0.0"
#define AppExe "CommandCenter.exe"

[Setup]
AppId={{B6C3A1E2-5D47-4F0A-9C21-7E3B1D9A4C58}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Command Center
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; No administrator prompt: installs for the current user only (Program Files not needed).
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=installer_output
OutputBaseFilename=CommandCenter_Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
LicenseFile=TERMS_AND_PRIVACY.txt
UninstallDisplayIcon={app}\{#AppExe}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; Flags: unchecked

[Files]
Source: "dist\CommandCenter\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Start {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; Make sure the app (and its tray icon) is closed so every file can be removed.
Filename: "{sys}\taskkill.exe"; Parameters: "/im {#AppExe} /f"; Flags: runhidden; RunOnceId: "StopApp"

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    // No leftovers: remove the "Start with Windows" entry the app created.
    RegDeleteValue(HKEY_CURRENT_USER, 'Software\Microsoft\Windows\CurrentVersion\Run', 'CommandCenter');
    RegDeleteValue(HKEY_CURRENT_USER, 'Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run', 'CommandCenter');
    // Your settings and voice commands: keep them unless the user says to delete them.
    DataDir := ExpandConstant('{userappdata}\CommandCenter');
    if DirExists(DataDir) then
      if MsgBox('Also delete your Command Center settings and voice commands?' + #13#10 +
                'Choose No if you plan to install it again.', mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(DataDir, True, True, True);
  end;
end;
