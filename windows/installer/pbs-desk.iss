; PBS-Desk Setup (Inno Setup 6)
; Bauen: build.ps1 legt stage\ an (Python + PySide6, Engine, Programme) und ruft
;   ISCC.exe /DAppVersion=<Version> pbs-desk.iss
; Installieren ohne Rueckfragen:
;   PBS-Desk-Setup-<Version>.exe /VERYSILENT /SUPPRESSMSGBOXES [/CONFIG=<pfad\pbs-desk.conf>]
; Eine vorhandene C:\ProgramData\PBS-Desk\pbs-desk.conf bleibt unveraendert.
; /CONFIG uebernimmt eine vorbereitete Datei (nur wenn noch keine Konfiguration da ist).
; Das Token-Secret steht nie auf einer Befehlszeile und nie im Setup-Log.

#ifndef AppVersion
  #define AppVersion "0.9.0"
#endif

[Setup]
AppId={{9B6F30AF-CC0E-43A9-A544-DEC1A14FD530}
AppName=PBS-Desk
AppVersion={#AppVersion}
AppVerName=PBS-Desk {#AppVersion}
AppPublisher=PBS-Desk
AppPublisherURL=https://github.com/Bu66as/pbs-desk
AppSupportURL=https://github.com/Bu66as/pbs-desk
VersionInfoVersion={#AppVersion}
; Die Programme erwarten feste Pfade (pbsdesk.py: PROG, DATEN)
DefaultDirName={commonpf64}\PBS-Desk
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=no
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
WizardStyle=modern
SetupIconFile=stage\icons\pbs-desk.ico
UninstallDisplayIcon={app}\icons\pbs-desk.ico
UninstallDisplayName=PBS-Desk
OutputDir=Output
OutputBaseFilename=PBS-Desk-Setup-{#AppVersion}
Compression=lzma2/max
SolidCompression=yes
LicenseFile=stage\LICENSE.txt
CloseApplications=no
SetupLogging=yes

[Languages]
Name: "german"; MessagesFile: "compiler:Languages\German.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "stage\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "fingerabdruck.ps1"; Flags: dontcopy
Source: "entfernen.ps1"; Flags: dontcopy

[Run]
Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\app\pbs-tray.pyw"""; WorkingDir: "{app}\app"; \
  Description: "{cm:TrayStarten}"; Flags: postinstall nowait runasoriginaluser skipifsilent

[UninstallRun]
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; \
  Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\installer\entfernen.ps1"""; \
  Flags: runhidden waituntilterminated; RunOnceId: "PBSDeskEntfernen"

[UninstallDelete]
; erzeugte Dateien (__pycache__ u. a.); die Daten unter ProgramData regelt der Code-Teil
Type: filesandordirs; Name: "{app}"

[CustomMessages]
german.TrayStarten=PBS-Desk im Infobereich starten
german.SeiteTitel=Backup-Server
german.SeiteText=Verbindung zum Proxmox Backup Server
german.Server=Server:
german.Port=Port:
german.Datastore=Datastore:
german.Namespace=Namespace:
german.BackupId=Backup-ID:
german.TokenId=API-Token:
german.Secret=Token-Secret:
german.Fingerprint=Fingerabdruck:
german.Holen=Vom Server holen
german.HinweisNeu=Server leer lassen, um ihn später unter „Einstellungen“ einzutragen. Namespace ist optional.
german.HinweisVorhanden=Es gibt schon eine Konfiguration. Sie wird unverändert übernommen, das Token-Secret bleibt gespeichert. Mit „Weiter“ bestätigen; ändern lässt sie sich später unter „Einstellungen“.
german.SecretVorhanden=(gespeichert)
german.OhneServer=Ohne Backup-Server installieren? Die Verbindung lässt sich später unter „Einstellungen“ eintragen.
german.Fehlt=Bitte ausfüllen: %1
german.FpFrage=Der Server meldet diesen Fingerabdruck:%n%n%1%n%nStimmt er mit dem im Dashboard des Backup-Servers überein?
german.FpFehler=Fingerabdruck nicht abrufbar: %1
german.ServerUngueltig=Server und Port prüfen.
german.EinrichtenFehler=Das Einrichten von Aufgaben und Autostart ist fehlgeschlagen (Exitcode %1). Setup erneut ausführen oder windows\install.ps1 -NurEinrichten als Administrator starten.
german.DatenFrage=Sollen auch die Daten unter %1 gelöscht werden (Zugangsdaten, Einstellungen, Verlauf)?%n%nBei „Nein“ bleiben sie für eine spätere Installation erhalten.
english.TrayStarten=Start PBS-Desk in the notification area
english.SeiteTitel=Backup server
english.SeiteText=Connection to the Proxmox Backup Server
english.Server=Server:
english.Port=Port:
english.Datastore=Datastore:
english.Namespace=Namespace:
english.BackupId=Backup ID:
english.TokenId=API token:
english.Secret=Token secret:
english.Fingerprint=Fingerprint:
english.Holen=Get from server
english.HinweisNeu=Leave the server empty to set it up later in Settings. Namespace is optional.
english.HinweisVorhanden=A configuration already exists and will be kept as is, including the stored token secret. Click Next to confirm. You can change it later in Settings.
english.SecretVorhanden=(stored)
english.OhneServer=Install without a backup server? You can add the connection later in Settings.
english.Fehlt=Please fill in: %1
english.FpFrage=The server reports this fingerprint:%n%n%1%n%nDoes it match the one shown in the backup server's dashboard?
english.FpFehler=Could not get the fingerprint: %1
english.ServerUngueltig=Check server and port.
english.EinrichtenFehler=Setting up the scheduled tasks and autostart failed (exit code %1). Run Setup again, or run windows\install.ps1 -NurEinrichten as administrator.
english.DatenFrage=Also delete the data in %1 (credentials, settings, history)?%n%nChoose No to keep it for a later installation.

[Code]
const
  F_SERVER = 0; F_PORT = 1; F_STORE = 2; F_NS = 3; F_ID = 4; F_TOKEN = 5; F_SECRET = 6; F_FP = 7;

var
  Seite: TWizardPage;
  Felder: array[0..7] of TNewEdit;
  Holen: TNewButton;
  Vorhanden: Boolean;

function Daten: String;
begin
  Result := ExpandConstant('{commonappdata}\PBS-Desk');
end;

function KonfPfad: String;
begin
  Result := Daten + '\pbs-desk.conf';
end;

function PowerShell: String;
begin
  Result := ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe');
end;

{ Wert KEY=... aus pbs-desk.conf; das Secret wird nie gelesen }
function KonfWert(const Zeilen: TArrayOfString; const Key: String): String;
var i: Integer; z: String;
begin
  Result := '';
  for i := 0 to GetArrayLength(Zeilen) - 1 do begin
    z := Trim(Zeilen[i]);
    if (Copy(z, 1, 1) <> '#') and (Pos(Key + '=', z) = 1) then
      Result := Trim(Copy(z, Length(Key) + 2, MaxInt));
  end;
end;

function Zeile(i: Integer; const Text: String; Breite: Integer): TNewEdit;
var L: TNewStaticText; y: Integer;
begin
  y := i * ScaleY(25);
  L := TNewStaticText.Create(Seite);
  L.Parent := Seite.Surface;
  L.Caption := Text;
  L.Left := 0;
  L.Top := y + ScaleY(3);
  Result := TNewEdit.Create(Seite);
  Result.Parent := Seite.Surface;
  Result.Left := ScaleX(110);
  Result.Top := y;
  Result.Width := Breite;
end;

function HostOk(const H: String): Boolean;
begin
  Result := (H <> '') and (Pos(' ', H) = 0) and (Pos('"', H) = 0) and (Pos('/', H) = 0)
    and (Pos('''', H) = 0) and (Pos('&', H) = 0) and (Pos(';', H) = 0);
end;

procedure HolenClick(Sender: TObject);
var Ziel, Arg: String; Inhalt: AnsiString; rc: Integer;
begin
  if not HostOk(Trim(Felder[F_SERVER].Text)) or (StrToIntDef(Trim(Felder[F_PORT].Text), 0) <= 0) then begin
    MsgBox(CustomMessage('ServerUngueltig'), mbError, MB_OK);
    exit;
  end;
  ExtractTemporaryFile('fingerabdruck.ps1');
  Ziel := ExpandConstant('{tmp}\fingerabdruck.txt');
  DeleteFile(Ziel);
  Arg := '-NoProfile -ExecutionPolicy Bypass -File "' + ExpandConstant('{tmp}\fingerabdruck.ps1') +
         '" -Server "' + Trim(Felder[F_SERVER].Text) + '" -Port ' + IntToStr(StrToIntDef(Trim(Felder[F_PORT].Text), 8007)) +
         ' -Ziel "' + Ziel + '"';
  Exec(PowerShell, Arg, '', SW_HIDE, ewWaitUntilTerminated, rc);
  if not LoadStringFromFile(Ziel, Inhalt) then Inhalt := 'FEHLER ?';
  Inhalt := Trim(Inhalt);
  if Copy(Inhalt, 1, 3) = 'OK ' then begin
    if MsgBox(FmtMessage(CustomMessage('FpFrage'), [Copy(Inhalt, 4, MaxInt)]), mbConfirmation, MB_YESNO) = IDYES then
      Felder[F_FP].Text := Copy(Inhalt, 4, MaxInt);
  end else
    MsgBox(FmtMessage(CustomMessage('FpFehler'), [Copy(Inhalt, 8, MaxInt)]), mbError, MB_OK);
end;

procedure InitializeWizard;
var Zeilen: TArrayOfString; Repo, Host, Port: String; i, p, b: Integer; Hinweis: TNewStaticText;
begin
  Vorhanden := False;
  if LoadStringsFromFile(KonfPfad, Zeilen) then
    Vorhanden := KonfWert(Zeilen, 'PBS_REPOSITORY') <> '';

  Seite := CreateCustomPage(wpSelectTasks, CustomMessage('SeiteTitel'), CustomMessage('SeiteText'));
  b := Seite.SurfaceWidth - ScaleX(110);
  Felder[F_SERVER] := Zeile(0, CustomMessage('Server'), b);
  Felder[F_PORT] := Zeile(1, CustomMessage('Port'), ScaleX(70));
  Felder[F_STORE] := Zeile(2, CustomMessage('Datastore'), b);
  Felder[F_NS] := Zeile(3, CustomMessage('Namespace'), b);
  Felder[F_ID] := Zeile(4, CustomMessage('BackupId'), b);
  Felder[F_TOKEN] := Zeile(5, CustomMessage('TokenId'), b);
  Felder[F_SECRET] := Zeile(6, CustomMessage('Secret'), b);
  Felder[F_SECRET].PasswordChar := '*';
  Felder[F_FP] := Zeile(7, CustomMessage('Fingerprint'), b - ScaleX(130));
  Holen := TNewButton.Create(Seite);
  Holen.Parent := Seite.Surface;
  Holen.Caption := CustomMessage('Holen');
  Holen.Left := Seite.SurfaceWidth - ScaleX(124);
  Holen.Top := Felder[F_FP].Top - ScaleY(1);
  Holen.Width := ScaleX(124);
  Holen.Height := ScaleY(23);
  Holen.OnClick := @HolenClick;
  Hinweis := TNewStaticText.Create(Seite);
  Hinweis.Parent := Seite.Surface;
  Hinweis.Top := 8 * ScaleY(25) + ScaleY(4);
  Hinweis.Width := Seite.SurfaceWidth;
  Hinweis.AutoSize := False;
  Hinweis.Height := ScaleY(42);
  Hinweis.WordWrap := True;

  Felder[F_PORT].Text := '8007';
  Felder[F_ID].Text := Lowercase(GetComputerNameString);
  Felder[F_TOKEN].Text := '';
  if Vorhanden then begin
    Repo := KonfWert(Zeilen, 'PBS_REPOSITORY');
    p := Pos('://', Repo);
    if p > 0 then Repo := Copy(Repo, p + 3, MaxInt);
    if (Length(Repo) > 0) and (Repo[Length(Repo)] = '/') then Repo := Copy(Repo, 1, Length(Repo) - 1);
    Host := Repo; Port := '8007';
    p := Pos(':', Repo);
    if p > 0 then begin Host := Copy(Repo, 1, p - 1); Port := Copy(Repo, p + 1, MaxInt); end;
    Felder[F_SERVER].Text := Host;
    Felder[F_PORT].Text := Port;
    Felder[F_STORE].Text := KonfWert(Zeilen, 'PBS_DATASTORE');
    Felder[F_NS].Text := KonfWert(Zeilen, 'PBS_NAMESPACE');
    Felder[F_ID].Text := KonfWert(Zeilen, 'PBS_BACKUP_ID');
    Felder[F_TOKEN].Text := KonfWert(Zeilen, 'PBS_TOKEN_ID');
    Felder[F_FP].Text := KonfWert(Zeilen, 'PBS_FINGERPRINT');
    Felder[F_SECRET].PasswordChar := #0;
    Felder[F_SECRET].Text := CustomMessage('SecretVorhanden');
    for i := 0 to 7 do Felder[i].Enabled := False;
    Holen.Enabled := False;
    Hinweis.Caption := CustomMessage('HinweisVorhanden');
  end else
    Hinweis.Caption := CustomMessage('HinweisNeu');
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var Fehlt: String;
begin
  Result := True;
  if WizardSilent or (CurPageID <> Seite.ID) or Vorhanden then exit;
  if Trim(Felder[F_SERVER].Text) = '' then begin
    Result := MsgBox(CustomMessage('OhneServer'), mbConfirmation, MB_YESNO) = IDYES;
    exit;
  end;
  if not HostOk(Trim(Felder[F_SERVER].Text)) or (StrToIntDef(Trim(Felder[F_PORT].Text), 0) <= 0) then begin
    MsgBox(CustomMessage('ServerUngueltig'), mbError, MB_OK);
    Result := False;
    exit;
  end;
  Fehlt := '';
  if Trim(Felder[F_STORE].Text) = '' then Fehlt := Fehlt + ' ' + CustomMessage('Datastore');
  if Trim(Felder[F_ID].Text) = '' then Fehlt := Fehlt + ' ' + CustomMessage('BackupId');
  if Trim(Felder[F_TOKEN].Text) = '' then Fehlt := Fehlt + ' ' + CustomMessage('TokenId');
  if Trim(Felder[F_SECRET].Text) = '' then Fehlt := Fehlt + ' ' + CustomMessage('Secret');
  if Trim(Felder[F_FP].Text) = '' then Fehlt := Fehlt + ' ' + CustomMessage('Fingerprint');
  if Fehlt <> '' then begin
    MsgBox(FmtMessage(CustomMessage('Fehlt'), [Trim(Fehlt)]), mbError, MB_OK);
    Result := False;
  end;
end;

{ Laufende Tray-/Fensterprozesse vor dem Kopieren beenden (Update) }
function PrepareToInstall(var NeedsRestart: Boolean): String;
var rc: Integer;
begin
  Result := '';
  ExtractTemporaryFile('entfernen.ps1');
  Exec(PowerShell, '-NoProfile -ExecutionPolicy Bypass -File "' + ExpandConstant('{tmp}\entfernen.ps1') + '" -NurStoppen',
       '', SW_HIDE, ewWaitUntilTerminated, rc);
end;

{ Neue Konfiguration schreiben. install.ps1 hat die Datei vorher mit
  Rechten nur fuer SYSTEM und Administratoren angelegt; Ueberschreiben
  behaelt diese Rechte. Kein Log-Eintrag mit Inhalten. }
procedure KonfSchreiben;
var Z: TArrayOfString; Quelle: String; Ns: String;
begin
  Quelle := ExpandConstant('{param:CONFIG|}');
  if Vorhanden then exit;
  if WizardSilent then begin
    if (Quelle = '') or not LoadStringsFromFile(Quelle, Z) then exit;
    if KonfWert(Z, 'PBS_REPOSITORY') = '' then exit;
    SaveStringsToUTF8File(KonfPfad, Z, False);
    Log('pbs-desk.conf aus /CONFIG uebernommen');
    exit;
  end;
  if Trim(Felder[F_SERVER].Text) = '' then exit;
  Ns := Trim(Felder[F_NS].Text);
  SetArrayLength(Z, 8);
  Z[0] := '# PBS-Desk Windows - nur SYSTEM und Administratoren lesbar';
  Z[1] := 'PBS_REPOSITORY=https://' + Trim(Felder[F_SERVER].Text) + ':' + IntToStr(StrToIntDef(Trim(Felder[F_PORT].Text), 8007));
  Z[2] := 'PBS_DATASTORE=' + Trim(Felder[F_STORE].Text);
  Z[3] := 'PBS_NAMESPACE=' + Ns;
  Z[4] := 'PBS_BACKUP_ID=' + Trim(Felder[F_ID].Text);
  Z[5] := 'PBS_TOKEN_ID=' + Trim(Felder[F_TOKEN].Text);
  Z[6] := 'PBS_TOKEN_SECRET=' + Trim(Felder[F_SECRET].Text);
  Z[7] := 'PBS_FINGERPRINT=' + Trim(Felder[F_FP].Text);
  SaveStringsToUTF8File(KonfPfad, Z, False);
  Felder[F_SECRET].Text := '';
  Log('pbs-desk.conf geschrieben (ohne Ausgabe der Werte)');
end;

procedure Einrichten;
var rc: Integer;
begin
  Exec(PowerShell, '-NoProfile -ExecutionPolicy Bypass -File "' + ExpandConstant('{app}\installer\install.ps1') + '" -NurEinrichten',
       ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, rc);
  Log('install.ps1 -NurEinrichten: Exitcode ' + IntToStr(rc));
  if rc <> 0 then
    SuppressibleMsgBox(FmtMessage(CustomMessage('EinrichtenFehler'), [IntToStr(rc)]), mbError, MB_OK, IDOK);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then begin
    Einrichten;      { Datenordner, Rechte, leere pbs-desk.conf, Aufgaben, Autostart }
    KonfSchreiben;
    Einrichten;      { Rechte der pbs-desk.conf erneut erzwingen }
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if (CurUninstallStep = usPostUninstall) and DirExists(Daten) and not UninstallSilent then
    if MsgBox(FmtMessage(CustomMessage('DatenFrage'), [Daten]), mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
      DelTree(Daten, True, True, True);
end;
