; Build: ISCC.exe installer\PDFMaster.iss (Inno Setup >= 6.2.2)
#define AppName "PDF Мастер"
#define AppVersion "0.3.0"
#define AppExeName "PDFMaster.exe"

[Setup]
AppId={{519E1AB0-9E92-42A6-B9F1-2B412B693910}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=PDF Мастер contributors
DefaultDirName={localappdata}\Programs\PDFMaster
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
MinVersion=10.0.22000
OutputDir=..\dist\installers
OutputBaseFilename=PDFMaster-Setup-{#AppVersion}
SetupIconFile=..\resources\icon.ico
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName}
Compression=lzma2/normal
SolidCompression=yes
WizardStyle=modern
LicenseFile=..\LICENSE.txt
CloseApplications=yes
RestartApplications=no
DisableWelcomePage=no
ChangesAssociations=no
SetupLogging=yes

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Ярлыки:"; Flags: unchecked

[Files]
Source: "..\dist\PDFMaster\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Запустить {#AppName}"; Flags: nowait postinstall skipifsilent
