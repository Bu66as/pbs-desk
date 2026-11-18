<#
.SYNOPSIS
  Prueft fuer die Setup.exe die Verbindung zum Backup-Server: Erreichbarkeit,
  Fingerabdruck und Anmeldung mit dem API-Token (wie pbsdesk.Server.pruefen).

.DESCRIPTION
  Das Token-Geheimnis kommt aus der Datei -GeheimDatei (im privaten Temp-Ordner
  des Setups), nie ueber die Befehlszeile. Ergebnis als eine Zeile in -Ziel:
    OK | ANMELDUNG | FINGERABDRUCK | UNERREICHBAR <text> | HTTP <code> | FEHLER <text>
#>
param([Parameter(Mandatory)][string]$Server, [int]$Port = 8007,
      [Parameter(Mandatory)][string]$Datastore, [string]$Namespace = "",
      [Parameter(Mandatory)][string]$Token, [Parameter(Mandatory)][string]$Fingerabdruck,
      [Parameter(Mandatory)][string]$GeheimDatei, [Parameter(Mandatory)][string]$Ziel)
$ErrorActionPreference = "Stop"
function Ergebnis($t) { Set-Content -Encoding ASCII $Ziel $t; exit 0 }
try {
    $geheim = (Get-Content -Raw $GeheimDatei).Trim()
} catch { Ergebnis "FEHLER Geheimnis nicht lesbar" }
$tcp = New-Object Net.Sockets.TcpClient
try {
    if (-not $tcp.ConnectAsync($Server, $Port).Wait(8000)) { throw "Zeitueberschreitung" }
} catch { Ergebnis ("UNERREICHBAR " + $_.Exception.GetBaseException().Message) }
try {
    $ssl = New-Object Net.Security.SslStream($tcp.GetStream(), $false, ({ $true } -as [Net.Security.RemoteCertificateValidationCallback]))
    $ssl.ReadTimeout = 15000
    $ssl.AuthenticateAsClient($Server)
    $h = [Security.Cryptography.SHA256]::Create().ComputeHash($ssl.RemoteCertificate.GetRawCertData())
    $echt = ($h | ForEach-Object { $_.ToString("x2") }) -join ""
    if ($echt -ne ($Fingerabdruck -replace ":", "").Trim().ToLower()) { Ergebnis "FINGERABDRUCK" }
    $pfad = "/api2/json/admin/datastore/" + [Uri]::EscapeDataString($Datastore) + "/groups"
    if ($Namespace) { $pfad += "?ns=" + [Uri]::EscapeDataString($Namespace) }
    $anfrage = "GET $pfad HTTP/1.1`r`nHost: ${Server}:$Port`r`nAuthorization: PBSAPIToken=${Token}:$geheim`r`nConnection: close`r`n`r`n"
    $b = [Text.Encoding]::UTF8.GetBytes($anfrage)
    $ssl.Write($b, 0, $b.Length)
    $ssl.Flush()
    $zeile = (New-Object IO.StreamReader($ssl)).ReadLine()
    $ssl.Dispose(); $tcp.Close()
    $code = [int](($zeile -split " ")[1])
    if ($code -eq 200) { Ergebnis "OK" }
    if ($code -eq 401) { Ergebnis "ANMELDUNG" }
    Ergebnis "HTTP $code"
} catch {
    Ergebnis ("FEHLER " + $_.Exception.GetBaseException().Message)
}
