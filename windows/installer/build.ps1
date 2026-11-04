<#
.SYNOPSIS
  Baut PBS-Desk-Setup-<Version>.exe (Inno Setup) unter Windows.

.DESCRIPTION
  Legt unter windows\installer\stage alles ab, was die Setup.exe mitbringt,
  damit beim Installieren kein Internet noetig ist:
    stage\python   Python (NuGet-Paket "python") mit PySide6-Essentials
    stage\bin      Engine aus proxmoxbackupclient_go (Release, gegen checksums.txt geprueft)
                   samt LICENSE und README der Engine
    stage\app      Programme aus windows\
    stage\icons    SVG-Symbole und pbs-desk.ico
    stage\locale   englische Uebersetzungen (.mo)
  Danach ruft es ISCC.exe mit /DAppVersion=<Version> auf.
  Herkunft und Lizenz der Engine: THIRD-PARTY.md.
#>
param(
    [string]$Version = "0.9.0",
    [string]$PythonVersion = "3.12.10",
    [string]$EngineVersion = "v1.1.3",
    [string]$Iscc = ""
)
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$Hier = $PSScriptRoot
$Win = Split-Path -Parent $Hier
$Repo = Split-Path -Parent $Win
$Stage = Join-Path $Hier "stage"
$Laden = Join-Path $Hier "downloads"
function Schritt($t) { Write-Host "== $t" }
function Pruefe($was) { if ($LASTEXITCODE -ne 0) { throw "$was fehlgeschlagen (Exitcode $LASTEXITCODE)" } }

Remove-Item -Recurse -Force $Stage, $Laden -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $Stage, $Laden, "$Stage\bin", "$Stage\app", "$Stage\icons" | Out-Null

# --- Python und PySide6 --------------------------------------------------------
Schritt "Python $PythonVersion"
$nupkg = Join-Path $Laden "python.zip"
Invoke-WebRequest -UseBasicParsing "https://www.nuget.org/api/v2/package/python/$PythonVersion" -OutFile $nupkg
Expand-Archive $nupkg -DestinationPath "$Laden\python"
Copy-Item -Recurse "$Laden\python\tools" "$Stage\python"
$Py = Join-Path $Stage "python\python.exe"
& $Py -m ensurepip --default-pip; Pruefe "ensurepip"
& $Py -m pip install --disable-pip-version-check --no-warn-script-location --no-compile PySide6-Essentials; Pruefe "pip install PySide6-Essentials"
& $Py -c "import PySide6; print('PySide6', PySide6.__version__)"; Pruefe "import PySide6"

# --- Engine ----------------------------------------------------------------------
Schritt "Engine proxmoxbackupclient_go $EngineVersion"
$basis = "https://github.com/tizbac/proxmoxbackupclient_go/releases/download/$EngineVersion"
$zipName = "proxmoxbackupclient_go_Windows_x86_64.zip"
Invoke-WebRequest -UseBasicParsing "$basis/$zipName" -OutFile "$Laden\$zipName"
Invoke-WebRequest -UseBasicParsing "$basis/checksums.txt" -OutFile "$Laden\checksums.txt"
$soll = (Get-Content "$Laden\checksums.txt" | Where-Object { $_ -match "\s$([regex]::Escape($zipName))$" }) -replace "\s.*$", ""
$ist = (Get-FileHash -Algorithm SHA256 "$Laden\$zipName").Hash.ToLower()
if (-not $soll -or $ist -ne $soll.ToLower()) { throw "Pruefsumme der Engine stimmt nicht: ist $ist, soll $soll" }
Write-Host "SHA256 ok: $ist"
Expand-Archive "$Laden\$zipName" -DestinationPath "$Laden\engine"
Copy-Item "$Laden\engine\pbsdirectorybackup.exe" "$Stage\bin\proxmoxbackup-directory.exe"
Copy-Item "$Laden\engine\pbsmachinebackup.exe" "$Stage\bin\pbsmachinebackup.exe"
Copy-Item "$Laden\engine\LICENSE" "$Stage\bin\LICENSE-proxmoxbackupclient_go.txt"
Copy-Item "$Laden\engine\README.md" "$Stage\bin\README-proxmoxbackupclient_go.md"
Copy-Item "$Hier\THIRD-PARTY.md" "$Stage\bin\THIRD-PARTY.md"

# --- Programme, Symbole, Uebersetzungen -------------------------------------------
Schritt "Programme"
Copy-Item "$Win\*.py", "$Win\*.pyw" "$Stage\app\"
Copy-Item "$Repo\icons\*.svg" "$Stage\icons\"
Copy-Item "$Repo\LICENSE" "$Stage\LICENSE.txt"
New-Item -ItemType Directory -Force "$Stage\installer", "$Stage\locale\en\LC_MESSAGES" | Out-Null
Copy-Item "$Win\install.ps1", "$Hier\entfernen.ps1" "$Stage\installer\"
$po = (Get-ChildItem "$Repo\po\en\*.po").FullName
& $Py "$Repo\tools\msgfmt.py" "$Stage\locale\en\LC_MESSAGES\pbs-desk.mo" @po; Pruefe "msgfmt"
$env:QT_QPA_PLATFORM = "offscreen"
& $Py -c "import sys;from PySide6.QtGui import QGuiApplication,QIcon;a=QGuiApplication(['x']);ok=QIcon(sys.argv[1]).pixmap(256,256).save(sys.argv[2],'ICO');sys.exit(0 if ok else 1)" "$Stage\icons\pbs-desk.svg" "$Stage\icons\pbs-desk.ico"
Pruefe "pbs-desk.ico"

# --- Setup.exe ---------------------------------------------------------------------
Schritt "Inno Setup"
if (-not $Iscc) {
    $Iscc = @((Get-Command iscc.exe -ErrorAction SilentlyContinue).Source,
              "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
              "$env:ProgramFiles\Inno Setup 6\ISCC.exe") | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
}
if (-not $Iscc) { throw "ISCC.exe nicht gefunden (Inno Setup 6 installieren)" }
& $Iscc "/DAppVersion=$Version" "$Hier\pbs-desk.iss"; Pruefe "ISCC"
Get-ChildItem "$Hier\Output\PBS-Desk-Setup-*.exe" | ForEach-Object { "{0}  {1:N1} MB" -f $_.Name, ($_.Length / 1MB) }
