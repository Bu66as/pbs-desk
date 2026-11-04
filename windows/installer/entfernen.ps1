<#
.SYNOPSIS
  Gegenstueck zu install.ps1 fuer die Deinstallation (ruft die Setup.exe auf).

.DESCRIPTION
  Beendet Tray und Fenster von PBS-Desk, entfernt die Aufgaben unter \PBS-Desk,
  den Tray-Autostart (HKLM Run "PBS-Desk") und die Startmenue-Verknuepfung.
  -NurStoppen beendet nur die laufenden Programme (vor einem Update).
  Die Daten unter C:\ProgramData\PBS-Desk fasst das Skript nicht an.
#>
param([switch]$NurStoppen)
$ErrorActionPreference = "Continue"
$Prog = "C:\Program Files\PBS-Desk"

# Tray, Einstellungen und Wiederherstellen laufen als pythonw/python aus $Prog\python
Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" |
    Where-Object { $_.ExecutablePath -and $_.ExecutablePath.StartsWith("$Prog\", "OrdinalIgnoreCase") } |
    ForEach-Object { Invoke-CimMethod -InputObject $_ -MethodName Terminate | Out-Null }
if ($NurStoppen) { exit 0 }

Get-ScheduledTask -TaskPath "\PBS-Desk\" -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-ScheduledTask -InputObject $_ -ErrorAction SilentlyContinue; Unregister-ScheduledTask -InputObject $_ -Confirm:$false }
try {
    $dienst = New-Object -ComObject "Schedule.Service"; $dienst.Connect()
    $dienst.GetFolder("\").DeleteFolder("PBS-Desk", 0)
} catch { }
Remove-ItemProperty "HKLM:\Software\Microsoft\Windows\CurrentVersion\Run" -Name "PBS-Desk" -ErrorAction SilentlyContinue
Remove-Item "$env:ProgramData\Microsoft\Windows\Start Menu\Programs\PBS-Desk.lnk" -ErrorAction SilentlyContinue
exit 0
