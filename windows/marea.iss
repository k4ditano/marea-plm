#ifndef Payload
  #error Supply /DPayload=... from build-installer.py
#endif
#ifndef AppVersion
  #error Supply /DAppVersion=...
#endif
[Setup]
AppId={{A8D741A8-45D5-4DE8-A38E-27DA65D253F8}
AppName=Marea Windows
AppVersion={#AppVersion}
AppPublisher=Marea contributors
AppPublisherURL=https://github.com/k4ditano/marea-plm
AppSupportURL=https://github.com/k4ditano/marea-plm/issues
DefaultDirName={localappdata}\Programs\Marea
DefaultGroupName=Marea Windows
DisableProgramGroupPage=no
PrivilegesRequired=lowest
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
MinVersion=10.0.17763
LicenseFile={#Payload}\app\LICENSE
InfoBeforeFile=installer-notes.txt
UninstallDisplayName=Marea Windows
SetupIconFile={#Payload}\app\assets\marea.ico
UninstallDisplayIcon={app}\app\assets\marea.ico
OutputBaseFilename=Marea-{#AppVersion}-windows-x64-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=no
RestartApplications=no
SetupLogging=yes
ChangesEnvironment=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; Flags: unchecked

[Files]
Source: "{#Payload}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Dirs]
Name: "{app}\logs"; Flags: uninsneveruninstall

[Icons]
Name: "{group}\Marea"; Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoLogo -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File ""{app}\windows\desktop.ps1"" start"; WorkingDir: "{app}"; IconFilename: "{app}\app\assets\marea.ico"
Name: "{group}\Uninstall Marea"; Filename: "{uninstallexe}"
Name: "{userdesktop}\Marea"; Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoLogo -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File ""{app}\windows\desktop.ps1"" start"; Tasks: desktopicon; IconFilename: "{app}\app\assets\marea.ico"

[Run]
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoLogo -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File ""{app}\windows\desktop.ps1"" start"; Description: "{cm:LaunchProgram,Marea}"; Flags: postinstall unchecked skipifsilent runhidden

[Code]
function RunHook(Root, Action, Extra, ResultPath: String): Boolean;
var
  Code: Integer;
  Params: String;
begin
  Params := '-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' + Root +
    '\windows\installer-hooks.ps1" -Package "' + Root + '" -Action ' + Action +
    ' -ResultFile "' + ResultPath + '" ' + Extra;
  Result := Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'), Params, '',
    SW_HIDE, ewWaitUntilTerminated, Code) and (Code = 0);
end;

function FailureMessage(ResultPath: String): String;
var Detail: AnsiString;
begin
  Result := 'Marea could not complete its package checks. See ' + ResultPath;
  if LoadStringFromFile(ResultPath, Detail) then Result := Result + #13#10 + Utf8Decode(Detail);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var Root, ResultPath: String;
begin
  ExtractTemporaryFiles('{app}\*');
  Root := ExpandConstant('{tmp}\') + '{app}';
  ResultPath := ExpandConstant('{tmp}\marea-preflight.txt');
  Result := '';
  if not RunHook(Root, 'prepare', '-Target "' + ExpandConstant('{app}') + '"', ResultPath) then
    Result := FailureMessage(ResultPath);
end;

procedure CurStepChanged(CurStep: TSetupStep);
var ResultPath: String;
begin
  if CurStep = ssPostInstall then begin
    ResultPath := ExpandConstant('{app}\logs\setup-registration.txt');
    if not RunHook(ExpandConstant('{app}'), 'register', '-Shortcut "' +
      ExpandConstant('{group}\Marea.lnk') + '"', ResultPath) then
      RaiseException(FailureMessage(ResultPath));
  end;
end;

function InitializeUninstall(): Boolean;
var ResultPath: String;
begin
  ResultPath := ExpandConstant('{tmp}\marea-stop.txt');
  Result := RunHook(ExpandConstant('{app}'), 'stop', '', ResultPath);
  if not Result then SuppressibleMsgBox(FailureMessage(ResultPath), mbError, MB_OK, IDOK);
end;
