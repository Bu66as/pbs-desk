<#
.SYNOPSIS
  Installiert PBS-Desk (Tray, Einstellungen, Wiederherstellen, Sicherungslauf) unter Windows.

.DESCRIPTION
  Gegenstueck zu install.sh. Aus dem entpackten Repo als Administrator starten:
    powershell -ExecutionPolicy Bypass -File windows\install.ps1

  - Python (eigenes, privates Python aus dem NuGet-Paket, kein PATH, keine
    Registrierung) und PySide6 nach C:\Program Files\PBS-Desk\python.
    -PaketOrdner <ordner> nimmt python-<ver>.nupkg und die Wheels aus einem
    Ordner statt aus dem Internet (gebuendeltes Paket).
  - Programme nach C:\Program Files\PBS-Desk\app, Symbole nach \icons,
    englische Texte aus po\en nach \locale.
  - Daten unter C:\ProgramData\PBS-Desk (pbs-desk.conf bleibt nur fuer SYSTEM
    und Administratoren lesbar, einstellungen.conf/verlauf.jsonl fuer alle).
  - Aufgaben \PBS-Desk\Sicherung (SYSTEM, taeglich) und \PBS-Desk\Sicherung-Hand
    (SYSTEM, ohne Ausloeser, von angemeldeten Benutzern startbar).
  - Tray-Autostart fuer alle Benutzer: HKLM\...\Run "PBS-Desk".
  Die Engine (bin\proxmoxbackup-directory.exe) richtet Etappe 1 ein.

  -NurEinrichten ueberspringt Python, PySide6 und das Kopieren der Programme
  und richtet nur Daten, Rechte, Aufgaben und Autostart ein. So ruft die
  Setup.exe (installer\pbs-desk.iss) das Skript auf, nachdem sie die Dateien
  selbst nach C:\Program Files\PBS-Desk gelegt hat.
#>
param(
    [string]$PaketOrdner = "",
    [switch]$NurEinrichten,
    [string]$PythonVersion = "3.12.10"
)
$ErrorActionPreference = "Stop"
$Prog  = "C:\Program Files\PBS-Desk"
$Daten = "C:\ProgramData\PBS-Desk"
$Quelle = Split-Path -Parent $PSScriptRoot     # Repo-Wurzel
$Py  = Join-Path $Prog "python\python.exe"
$Pyw = Join-Path $Prog "python\pythonw.exe"

$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
         ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) { throw "Bitte als Administrator starten." }
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
function Schritt($t) { Write-Host "== $t" }
# Native Programme schreiben Warnungen nach stderr; unter PowerShell 5.1 mit
# ErrorAction Stop waere das ein Abbruch. Fehler zaehlen nur ueber den Exitcode.
function Nativ {
    $alt = $ErrorActionPreference; $ErrorActionPreference = "Continue"
    & $args[0] @($args | Select-Object -Skip 1) 2>&1 | ForEach-Object { "$_" } | Out-Host
    $ErrorActionPreference = $alt
}

# --- Python und PySide6 ------------------------------------------------------
if (-not $NurEinrichten) {
New-Item -ItemType Directory -Force "$Prog\bin", "$Prog\app", "$Prog\icons" | Out-Null
if (-not (Test-Path $Py)) {
    Schritt "Python $PythonVersion"
    $tmp = Join-Path $env:TEMP "pbs-desk-python"
    Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
    New-Item -ItemType Directory $tmp | Out-Null
    $nupkg = Join-Path $tmp "python.zip"
    $lokal = if ($PaketOrdner) { Get-ChildItem $PaketOrdner -Filter "python*.nupkg" | Select-Object -First 1 }
    if ($lokal) { Copy-Item $lokal.FullName $nupkg }
    else { Invoke-WebRequest -UseBasicParsing "https://www.nuget.org/api/v2/package/python/$PythonVersion" -OutFile $nupkg }
    Expand-Archive $nupkg -DestinationPath "$tmp\x"
    Copy-Item -Recurse "$tmp\x\tools" "$Prog\python"
    Remove-Item -Recurse -Force $tmp
}
Nativ $Py -c "import PySide6"
if ($LASTEXITCODE -ne 0) {
    Schritt "PySide6"
    Nativ $Py -m ensurepip --default-pip
    $pip = @("-m", "pip", "install", "--disable-pip-version-check", "--no-warn-script-location", "PySide6-Essentials")
    if ($PaketOrdner) { $pip += @("--no-index", "--find-links", $PaketOrdner) }
    Nativ $Py @pip
    if ($LASTEXITCODE -ne 0) { throw "PySide6 liess sich nicht installieren." }
}

# --- Programme, Symbole, Uebersetzungen ---------------------------------------
Schritt "Programme"
Copy-Item -Force "$PSScriptRoot\*.py", "$PSScriptRoot\*.pyw" "$Prog\app\"
Copy-Item -Force "$Quelle\icons\*.svg" "$Prog\icons\"
New-Item -ItemType Directory -Force "$Prog\locale\en\LC_MESSAGES" | Out-Null
$po = (Get-ChildItem "$Quelle\po\en\*.po").FullName
Nativ $Py "$Quelle\tools\msgfmt.py" "$Prog\locale\en\LC_MESSAGES\pbs-desk.mo" @po
if ($LASTEXITCODE -ne 0) { throw "Uebersetzungen nicht erzeugt." }
# Startmenue-Symbol: .ico aus dem SVG (Qt rendert, Windows-Verknuepfungen wollen .ico)
$env:QT_QPA_PLATFORM = "offscreen"
Nativ $Py -c "import sys;from PySide6.QtGui import QGuiApplication,QIcon;a=QGuiApplication(['x']);QIcon(sys.argv[1]).pixmap(256,256).save(sys.argv[2],'ICO')" "$Prog\icons\pbs-desk.svg" "$Prog\icons\pbs-desk.ico"

}  # Ende -not $NurEinrichten

# --- Daten und Rechte ----------------------------------------------------------
Schritt "Daten unter $Daten"
New-Item -ItemType Directory -Force $Daten, "$Daten\restore-test" | Out-Null
$sys = New-Object Security.Principal.SecurityIdentifier "S-1-5-18"
$adm = New-Object Security.Principal.SecurityIdentifier "S-1-5-32-544"
$usr = New-Object Security.Principal.SecurityIdentifier "S-1-5-32-545"
$erb = [Security.AccessControl.InheritanceFlags]"ContainerInherit,ObjectInherit"
$acl = New-Object Security.AccessControl.DirectorySecurity
$acl.SetAccessRuleProtection($true, $false)
foreach ($s in $sys, $adm) { $acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule $s, "FullControl", $erb, "None", "Allow")) }
$acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule $usr, "ReadAndExecute", $erb, "None", "Allow"))
Set-Acl $Daten $acl
$conf = "$Daten\pbs-desk.conf"
if (-not (Test-Path $conf)) {
    Set-Content -Encoding ASCII $conf "# PBS-Desk Windows - nur SYSTEM und Administratoren lesbar"
}
$facl = New-Object Security.AccessControl.FileSecurity
$facl.SetAccessRuleProtection($true, $false)
foreach ($s in $sys, $adm) { $facl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule $s, "FullControl", "Allow")) }
Set-Acl $conf $facl
# Engine-Konfiguration mit Token-Secret (pbs-backup.py, je Lauf): nur SYSTEM und Administratoren
New-Item -ItemType Directory -Force "$Daten\engine" | Out-Null
$eacl = New-Object Security.AccessControl.DirectorySecurity
$eacl.SetAccessRuleProtection($true, $false)
foreach ($s in $sys, $adm) { $eacl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule $s, "FullControl", $erb, "None", "Allow")) }
Set-Acl "$Daten\engine" $eacl
$einst = "$Daten\einstellungen.conf"
if (-not (Test-Path $einst)) {
    Set-Content -Encoding ASCII $einst @(
        "# PBS-Desk Einstellungen (pbs-settings)",
        "UHRZEITEN=07:30,12:30,18:00", "ARBEITSZEIT_SKIP=1", "WORK_START=8", "WORK_END=17",
        "TAGESSPERRE=1", "QUELLE=C:\", "VSS=1", "STALE_DAYS=3")
}
# Vermerk fuer den Tray, der pbs-desk.conf nicht lesen darf: ist ein Server eingetragen?
$eingerichtet = if ((Get-Content $conf -ErrorAction SilentlyContinue) -match "^PBS_REPOSITORY=\S") { "1" } else { "0" }
$zeilen = @(Get-Content $einst | Where-Object { $_ -notlike "EINGERICHTET=*" }) + "EINGERICHTET=$eingerichtet"
Set-Content -Encoding ASCII $einst $zeilen
$uhrzeiten = ((Get-Content $einst | Where-Object { $_ -like "UHRZEITEN=*" }) -replace "^UHRZEITEN=", "")
if (-not $uhrzeiten) { $uhrzeiten = "07:30,12:30,18:00" }

# --- Aufgabenplanung -------------------------------------------------------------
Schritt "Aufgaben \PBS-Desk\Sicherung und \PBS-Desk\Sicherung-Hand"
$prinzipal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
$einstellung = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 12)
$ausloeser = @($uhrzeiten.Split(",") | ForEach-Object { New-ScheduledTaskTrigger -Daily -At $_.Trim() })
$backup = "`"$Prog\app\pbs-backup.py`""
Register-ScheduledTask -Force -TaskPath "\PBS-Desk\" -TaskName "Sicherung" -Principal $prinzipal `
    -Settings $einstellung -Trigger $ausloeser -Description "PBS-Desk: geplante Sicherung (Arbeitszeit- und Tagessperre)" `
    -Action (New-ScheduledTaskAction -Execute $Py -Argument "$backup --geplant" -WorkingDirectory "$Prog\app") | Out-Null
Register-ScheduledTask -Force -TaskPath "\PBS-Desk\" -TaskName "Sicherung-Hand" -Principal $prinzipal `
    -Settings $einstellung -Description "PBS-Desk: Sicherung von Hand aus dem Tray (ohne Sperren)" `
    -Action (New-ScheduledTaskAction -Execute $Py -Argument "$backup --hand" -WorkingDirectory "$Prog\app") | Out-Null
# Disk-Image: monatlich (nur wenn das letzte Image >= IMAGE_TAGE alt ist) und von Hand
$erste = $uhrzeiten.Split(",")[0].Trim()
$monatlich = New-ScheduledTaskTrigger -Weekly -WeeksInterval 4 -DaysOfWeek Saturday -At $erste
Register-ScheduledTask -Force -TaskPath "\PBS-Desk\" -TaskName "Image" -Principal $prinzipal `
    -Settings $einstellung -Trigger $monatlich -Description "PBS-Desk: Disk-Image der Systemplatte (alle 4 Wochen)" `
    -Action (New-ScheduledTaskAction -Execute $Py -Argument "$backup --image --geplant" -WorkingDirectory "$Prog\app") | Out-Null
Register-ScheduledTask -Force -TaskPath "\PBS-Desk\" -TaskName "Image-Hand" -Principal $prinzipal `
    -Settings $einstellung -Description "PBS-Desk: Disk-Image von Hand aus dem Tray" `
    -Action (New-ScheduledTaskAction -Execute $Py -Argument "$backup --image --hand" -WorkingDirectory "$Prog\app") | Out-Null
# Abbrechen einer laufenden Sicherung aus dem Tray (der Lauf gehoert SYSTEM)
Register-ScheduledTask -Force -TaskPath "\PBS-Desk\" -TaskName "Abbrechen" -Principal $prinzipal `
    -Settings (New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 5)) `
    -Description "PBS-Desk: laufende Sicherung abbrechen (aus dem Tray)" `
    -Action (New-ScheduledTaskAction -Execute $Py -Argument "$backup --abbrechen" -WorkingDirectory "$Prog\app") | Out-Null
# Angemeldete Benutzer duerfen den Handstart ausloesen (wie die polkit-Regel unter Linux)
$dienst = New-Object -ComObject "Schedule.Service"
$dienst.Connect()
foreach ($t in "Sicherung-Hand", "Image-Hand", "Abbrechen") {
    $dienst.GetFolder("\PBS-Desk").GetTask($t).SetSecurityDescriptor(
        "O:BAG:SYD:(A;;FA;;;SY)(A;;FA;;;BA)(A;;GRGX;;;AU)", 0)
}

# --- Autostart und Startmenue ------------------------------------------------------
Schritt "Tray-Autostart und Startmenue"
$tray = "`"$Pyw`" `"$Prog\app\pbs-tray.pyw`""
Set-ItemProperty "HKLM:\Software\Microsoft\Windows\CurrentVersion\Run" -Name "PBS-Desk" -Value $tray
$sh = New-Object -ComObject WScript.Shell
$lnk = $sh.CreateShortcut("$env:ProgramData\Microsoft\Windows\Start Menu\Programs\PBS-Desk.lnk")
$lnk.TargetPath = $Pyw
$lnk.Arguments = "`"$Prog\app\pbs-tray.pyw`""
$lnk.WorkingDirectory = "$Prog\app"
$lnk.Description = "PBS-Desk"
if (Test-Path "$Prog\icons\pbs-desk.ico") { $lnk.IconLocation = "$Prog\icons\pbs-desk.ico" }
$lnk.Save()

if (-not (Test-Path "$Prog\bin\proxmoxbackup-directory.exe")) {
    Write-Warning "Engine fehlt: $Prog\bin\proxmoxbackup-directory.exe"
}
Schritt "fertig"
