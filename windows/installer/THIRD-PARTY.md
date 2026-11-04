# Mitgelieferte Fremdsoftware (Windows-Setup)

Die Setup.exe von PBS-Desk bringt neben den eigenen Programmen drei fremde
Bestandteile mit. `build.ps1` lädt sie beim Bauen herunter, beim Installieren
ist kein Internet nötig.

## Engine: proxmoxbackupclient_go

| Feld          | Wert |
|---------------|------|
| Projekt       | tizbac/proxmoxbackupclient_go |
| Version       | v1.1.3 (Release vom 02.05.2026) |
| Quellcode     | https://github.com/tizbac/proxmoxbackupclient_go/tree/v1.1.3 |
| Download      | https://github.com/tizbac/proxmoxbackupclient_go/releases/download/v1.1.3/proxmoxbackupclient_go_Windows_x86_64.zip |
| Prüfsumme     | `checksums.txt` im selben Release, SHA-256 der Zip-Datei `78dfe3e02390580bace9733bc89277de2bbc87c0d478c3643ce74f8e9e53f879` |
| Lizenz        | GPL-3.0 (wie PBS-Desk) |

Aus der Zip-Datei landen unter `C:\Program Files\PBS-Desk\bin`:

| Datei im Release        | Datei im Setup                         |
|-------------------------|----------------------------------------|
| pbsdirectorybackup.exe  | proxmoxbackup-directory.exe            |
| pbsmachinebackup.exe    | pbsmachinebackup.exe                   |
| LICENSE                 | LICENSE-proxmoxbackupclient_go.txt     |
| README.md               | README-proxmoxbackupclient_go.md       |

Die Programme sind unverändert, nur `pbsdirectorybackup.exe` ist umbenannt.
`build.ps1` bricht ab, wenn die SHA-256-Prüfsumme nicht zu `checksums.txt`
passt. Den Quellcode genau dieser Fassung gibt es unter dem Tag v1.1.3 im
oben genannten Projekt (GPL-3.0, Abschnitt 6: Verweis auf den Quellcode).

## Python

Python 3.12.10 aus dem NuGet-Paket `python`
(https://www.nuget.org/packages/python/3.12.10), Python Software Foundation
License. Liegt privat unter `C:\Program Files\PBS-Desk\python`, ohne PATH-Eintrag
und ohne Registrierung.

## PySide6

PySide6-Essentials (Qt for Python) von PyPI, LGPL-3.0. Die Lizenztexte liegen
im Paket unter `python\Lib\site-packages\PySide6`. Quellcode:
https://code.qt.io/cgit/pyside/pyside-setup.git
