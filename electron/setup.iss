; ============================================================
; NFS-e Validador Nacional - Script Inno Setup
; Arquivo: electron/setup.iss
; ============================================================

#define AppName      "NFS-e Validador"
#ifndef AppVersion
  #define AppVersion "3.8.0"
#endif
#define AppPublisher "XMLVariavel"
#define AppExeName   "NFS-e Validador.exe"
#define AppId        "br.gov.nfse.validador"
#define AppURL       "https://github.com/XMLVariavel/nfse-validador"
#define SourceDir    "dist\win-unpacked"
#define OutputExe    "NFS-e-Validador-Setup-" + AppVersion

; ============================================================
[Setup]
AppId={#AppId}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DefaultDirName={localappdata}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DirExistsWarning=no
UsePreviousAppDir=yes
SetupIconFile=build\nfse.ico
UninstallDisplayIcon={app}\nfse.ico
UninstallDisplayName={#AppName}
OutputDir=dist
OutputBaseFilename={#OutputExe}
Compression=lzma2/ultra
SolidCompression=yes
WizardStyle=modern
WizardSizePercent=120
MinVersion=10.0

; ============================================================
[Languages]
Name: "ptbr"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

; ============================================================
[Tasks]
Name: "desktopicon";   Description: "Criar icone na Area de Trabalho";      GroupDescription: "Icones adicionais:"
Name: "startmenuicon"; Description: "Criar icone no Menu Iniciar";           GroupDescription: "Icones adicionais:"
Name: "autostart";     Description: "Iniciar automaticamente com Windows";   GroupDescription: "Inicializacao:"; Flags: unchecked

; ============================================================
[Dirs]
Name: "{app}";                          Permissions: users-full
Name: "{app}\resources";                Permissions: users-full
Name: "{app}\resources\app";            Permissions: users-full
Name: "{app}\resources\app\tabelas";    Permissions: users-full
Name: "{app}\resources\app\schemas";    Permissions: users-full
Name: "{app}\resources\app\static";     Permissions: users-full
Name: "{localappdata}\{#AppName}\logs"; Permissions: users-full

; ============================================================
[Files]

; Executavel principal
Source: "{#SourceDir}\{#AppExeName}"; DestDir: "{app}"; Flags: ignoreversion

; Icone
Source: "{#SourceDir}\nfse.ico"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist

; DLLs e binarios Electron na raiz
Source: "{#SourceDir}\*.dll";  DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceDir}\*.dat";  DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "{#SourceDir}\*.pak";  DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "{#SourceDir}\*.bin";  DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "{#SourceDir}\*.json"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist

; Locales
Source: "{#SourceDir}\locales\*"; DestDir: "{app}\locales"; Flags: ignoreversion recursesubdirs createallsubdirs

; Swiftshader
Source: "{#SourceDir}\swiftshader\*"; DestDir: "{app}\swiftshader"; Flags: ignoreversion recursesubdirs createallsubdirs skipifsourcedoesntexist

; Resources - asar
Source: "{#SourceDir}\resources\app.asar"; DestDir: "{app}\resources"; Flags: ignoreversion

; Resources - asar unpacked
Source: "{#SourceDir}\resources\app.asar.unpacked\*"; DestDir: "{app}\resources\app.asar.unpacked"; Flags: ignoreversion recursesubdirs createallsubdirs skipifsourcedoesntexist

; Scripts Python
Source: "{#SourceDir}\resources\app\server.py";            DestDir: "{app}\resources\app"; Flags: ignoreversion
Source: "{#SourceDir}\resources\app\launcher.py";          DestDir: "{app}\resources\app"; Flags: ignoreversion skipifsourcedoesntexist
Source: "{#SourceDir}\resources\app\monitorar_docs.py";    DestDir: "{app}\resources\app"; Flags: ignoreversion skipifsourcedoesntexist
Source: "{#SourceDir}\resources\app\atualizar_schemas.py"; DestDir: "{app}\resources\app"; Flags: ignoreversion skipifsourcedoesntexist
Source: "{#SourceDir}\resources\app\versao.json";          DestDir: "{app}\resources\app"; Flags: ignoreversion
Source: "{#SourceDir}\resources\app\nfse.ico";             DestDir: "{app}\resources\app"; Flags: ignoreversion skipifsourcedoesntexist

; sheets_config.json - NAO sobrescrever se ja existir
Source: "{#SourceDir}\resources\app\sheets_config.json"; DestDir: "{app}\resources\app"; Flags: onlyifdoesntexist skipifsourcedoesntexist

; Static (HTML, CSS, JS)
Source: "{#SourceDir}\resources\app\static\*"; DestDir: "{app}\resources\app\static"; Flags: ignoreversion recursesubdirs createallsubdirs

; Schemas XSD - NAO sobrescrever
Source: "{#SourceDir}\resources\app\schemas\*"; DestDir: "{app}\resources\app\schemas"; Flags: ignoreversion recursesubdirs createallsubdirs skipifsourcedoesntexist

; Tabelas - NAO sobrescrever dados do usuario
Source: "{#SourceDir}\resources\app\tabelas\*"; DestDir: "{app}\resources\app\tabelas"; Flags: onlyifdoesntexist recursesubdirs createallsubdirs skipifsourcedoesntexist

; Python embarcado
Source: "{#SourceDir}\resources\app\python\*"; DestDir: "{app}\resources\app\python"; Flags: ignoreversion recursesubdirs createallsubdirs skipifsourcedoesntexist

; ============================================================
[Icons]
Name: "{autodesktop}\{#AppName}";               Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\nfse.ico"; Tasks: desktopicon
Name: "{autostartmenu}\{#AppName}\{#AppName}";  Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\nfse.ico"; Tasks: startmenuicon
Name: "{autostartmenu}\{#AppName}\Desinstalar"; Filename: "{uninstallexe}";       Tasks: startmenuicon
Name: "{autostartup}\{#AppName}";               Filename: "{app}\{#AppExeName}"; Tasks: autostart

; ============================================================
[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{#AppId}"; ValueType: string; ValueName: "DisplayName";     ValueData: "{#AppName}";      Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{#AppId}"; ValueType: string; ValueName: "DisplayVersion";  ValueData: "{#AppVersion}";   Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{#AppId}"; ValueType: string; ValueName: "Publisher";       ValueData: "{#AppPublisher}"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{#AppId}"; ValueType: string; ValueName: "URLInfoAbout";    ValueData: "{#AppURL}";       Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{#AppId}"; ValueType: string; ValueName: "InstallLocation"; ValueData: "{app}";           Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{#AppId}"; ValueType: string; ValueName: "UninstallString"; ValueData: "{uninstallexe}";  Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{#AppId}"; ValueType: string; ValueName: "DisplayIcon";     ValueData: "{app}\nfse.ico";  Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{#AppId}"; ValueType: dword;  ValueName: "NoModify";        ValueData: 1;                 Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{#AppId}"; ValueType: dword;  ValueName: "NoRepair";        ValueData: 1;                 Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\AppUserModelId\{#AppId}"; ValueType: string; ValueName: "DisplayName"; ValueData: "{#AppName}"; Flags: uninsdeletekey

; ============================================================
[Run]
Filename: "{app}\{#AppExeName}"; Description: "Abrir {#AppName} agora"; Flags: nowait postinstall skipifsilent unchecked

; ============================================================
[UninstallRun]
Filename: "taskkill.exe"; Parameters: "/F /IM ""{#AppExeName}"" /T"; Flags: runhidden; RunOnceId: "KillApp"

; ============================================================
[UninstallDelete]
Type: dirifempty; Name: "{app}"

; ============================================================
[Code]

procedure KillRunningApp();
var
  ResultCode: Integer;
begin
  Exec('taskkill.exe', '/IM "NFS-e Validador.exe" /T', '',
    SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Sleep(1500);
  Exec('taskkill.exe', '/F /IM "NFS-e Validador.exe" /T', '',
    SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Sleep(500);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  KillRunningApp();
  Result := '';
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
    KillRunningApp();
end;

function GetUninstallString(): String;
var
  sUnInstPath: String;
  sUnInstallString: String;
begin
  sUnInstPath := 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{#AppId}';
  sUnInstallString := '';
  if not RegQueryStringValue(HKCU, sUnInstPath, 'UninstallString', sUnInstallString) then
    RegQueryStringValue(HKLM, sUnInstPath, 'UninstallString', sUnInstallString);
  Result := sUnInstallString;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  sUnInstallString: String;
  iResultCode: Integer;
begin
  if CurStep = ssInstall then
  begin
    sUnInstallString := GetUninstallString();
    if sUnInstallString <> '' then
    begin
      sUnInstallString := RemoveQuotes(sUnInstallString);
      Exec(sUnInstallString, '/SILENT', '', SW_HIDE, ewWaitUntilTerminated, iResultCode);
      Sleep(1000);
    end;
  end;
end;
