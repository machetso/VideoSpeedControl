; Copyright (c) 2026 Alex Vulcu
;
; Concept, architecture, direction, and curation by Alex Vulcu.
; Implementation assisted by generative AI tools.
;
; Licensed under the MIT License.
; See the LICENSE file in the repository root for details.
;
; Inno Setup 6 script – packs dist\VideoSpeedControl\ (PyInstaller) into one setup.exe.
;   iscc /DAppVersion=0.9.0 packaging\installer.iss   →   dist\VideoSpeedControl-0.9.0-setup.exe
; Installs per user by default (no admin rights needed); the setup offers "for all users".

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#define AppName "VideoSpeedControl"
#define AppExe "VideoSpeedControl.exe"

[Setup]
; never change the AppId – Windows uses it to find an older version for updates / uninstall
AppId={{6F0C9B2E-5D1A-4C7B-9E3F-2A8D4B6C1E70}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Alex Vulcu
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
LicenseFile=..\LICENSE
SetupIconFile=..\vsc\gui\resources\icon.ico
UninstallDisplayIcon={app}\{#AppExe}
OutputDir=..\dist
OutputBaseFilename={#AppName}-{#AppVersion}-setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "german"; MessagesFile: "compiler:Languages\German.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\{#AppName}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; an update replaces the whole bundle – no files left over from the previous version
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
