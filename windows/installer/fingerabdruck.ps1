<#
.SYNOPSIS
  Holt den SHA-256-Fingerabdruck des TLS-Zertifikats eines Backup-Servers
  (wie pbsdesk.fingerabdruck) und schreibt ihn in -Ziel. Fuer die Setup.exe.
#>
param([Parameter(Mandatory)][string]$Server, [int]$Port = 8007, [Parameter(Mandatory)][string]$Ziel)
$ErrorActionPreference = "Stop"
try {
    $tcp = New-Object Net.Sockets.TcpClient
    if (-not $tcp.ConnectAsync($Server, $Port).Wait(8000)) { throw "Zeitueberschreitung" }
    # Zertifikat absichtlich ungeprueft annehmen: es geht nur um den Fingerabdruck
    $ssl = New-Object Net.Security.SslStream($tcp.GetStream(), $false, ({ $true } -as [Net.Security.RemoteCertificateValidationCallback]))
    $ssl.AuthenticateAsClient($Server)
    $roh = $ssl.RemoteCertificate.GetRawCertData()
    $h = [Security.Cryptography.SHA256]::Create().ComputeHash($roh)
    $fp = ($h | ForEach-Object { $_.ToString("x2") }) -join ":"
    $ssl.Dispose(); $tcp.Close()
    Set-Content -Encoding ASCII $Ziel "OK $fp"
} catch {
    Set-Content -Encoding ASCII $Ziel ("FEHLER " + $_.Exception.GetBaseException().Message)
}
