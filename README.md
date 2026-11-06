# pbs-desk

[English](README.en.md)

Desktop-Client für Proxmox Backup Server: sichert Linux-Notebooks und -PCs
automatisch per `proxmox-backup-client`, zeigt den Zustand im Tray und holt
Dateien per Klick aus der Sicherung zurück.

Ein Projekt von ExNoLim. pbs-desk ist kein Produkt der Proxmox Server
Solutions GmbH, wird von ihr nicht unterstützt und ist nicht mit ihr verbunden.
Proxmox® ist eine eingetragene Marke der Proxmox Server Solutions GmbH in der
EU, den USA und anderen Ländern.

## Stand

Frühe Version. Im Alltag läuft pbs-desk seit Wochen auf mehreren Linux-Notebooks
(Fedora, KDE Plasma). Andere Distributionen und Desktops sind kaum erprobt.
Pakete (RPM/DEB) gibt es noch nicht, installiert wird unter Linux per `install.sh`, unter Windows per Setup.exe.

## Installation

Voraussetzungen: systemd, Python 3 mit PySide6, `notify-send`, `pkexec`,
`curl` und `proxmox-backup-client`. Optional `snapper` für btrfs-Snapshots.

Das System sollte vorher aktuell sein (`sudo dnf upgrade` bzw. `apt upgrade`).
Auf einem frisch installierten, nie aktualisierten Fedora kann `--deps` sonst
an Dateikonflikten zwischen Distributionspaketen scheitern.

```bash
git clone https://github.com/Bu66as/pbs-desk.git
cd pbs-desk
sudo ./install.sh --deps            # Abhängigkeiten per dnf/apt/zypper/pacman
# ohne Paket für proxmox-backup-client (z.B. Fedora, nur x86_64):
sudo ./install.sh --deps --with-client
```

Danach ab- und wieder anmelden. Im Tray: Rechtsklick > Einstellungen >
Backup-Server. Dort Server, Port, Datenspeicher, API-Token und Namespace
eintragen. Der Fingerabdruck des Servers wird abgerufen und angezeigt. Das Token
landet nur root-lesbar unter `/etc/proxmox-backup-client/lokal/`.

Auf dem Proxmox Backup Server braucht das Token auf dem Datenspeicher bzw.
Namespace die Rolle `DatastoreBackup`. Für das Wiederherstellen reicht sie
für die eigenen Sicherungen.

Entfernen: `sudo ./install.sh --uninstall` (Einstellungen bleiben) oder
`--purge` (alles weg).

Sprache: Oberfläche und Meldungen gibt es auf Deutsch und Englisch, gewählt
wird nach `LANGUAGE`/`LANG` (Deutsch bei `de*`, sonst Englisch). Das Protokoll
`/var/log/pbs-backup.log` ist deutsch.

## Was es heute kann

- Backup von `/` und `/home` als `root.pxar` und `home.pxar`
- Snapper-Snapshot (btrfs) vor dem Lauf, gesichert wird der eingefrorene Stand
- Eigener Server aus dem Einstellungsfenster, oder zentral vorgegeben zwei Ziele:
  im LAN ungedrosselt, unterwegs gedrosselt auf ein Offsite-Ziel
- Sperren: nicht in der Arbeitszeit, höchstens ein erfolgreicher Lauf pro Tag,
  nur am Netzteil
- Tray mit Status, Handschalter für die Drossel und Einstellungsdialog
- Im Tray abschaltbar: „Nach dem Backup herunterfahren“ (mit 60 s Countdown,
  nur nach erfolgreichem Lauf; bei Fehler oder Überspringen bleibt der Rechner an)
- Desktop-Meldungen bei Start, Erfolg und Fehler
- Wiederherstellen: Sicherungen auflisten, ein Archiv schreibgeschützt einhängen
  und im Dateimanager öffnen; dazu der Verlauf der Backup-Läufe

## Installation unter Windows

Voraussetzung: Windows 10 oder 11, 64 Bit, ein Konto mit Administratorrechten.
Python und alles Weitere bringt die Setup-Datei mit, beim Installieren ist
kein Internet nötig.

1. Die Setup.exe herunterladen (`PBS-Desk-Setup-<Version>.exe`). Solange es noch keinen Release
   gibt, liefert der Workflow „Windows setup“ (Actions) die Datei als Artefakt;
   man kann sie auch selbst bauen (`windows\installer\build.ps1`, braucht
   Inno Setup 6).
2. Doppelklick auf die Datei. Die Programme sind nicht signiert, deshalb zeigt
   Windows SmartScreen die Meldung „Der Computer wurde durch Windows geschützt“.
   Auf **Weitere Informationen** und dann auf **Trotzdem ausführen** klicken.
3. Der Assistent fragt nach der Sprache und zeigt die Lizenz. Auf der Seite
   „Backup-Server“ kommen Server, Port, Datenspeicher, Namespace, Backup-ID und
   API-Token hinein. „Vom Server holen“ ruft den Fingerabdruck ab. Das Token
   braucht auf dem Datenspeicher bzw. Namespace die Rolle `DatastoreBackup`.
4. Nach der Installation steht PBS-Desk unter „Apps“ > „Installierte Apps“
   (früher „Apps & Features“). Das Tray-Symbol liegt zunächst im Überlauf (`^`)
   der Taskleiste. Die Sicherung läuft als Aufgabe `\PBS-Desk\Sicherung`
   (morgens, mittags und abends) und das Disk-Image alle vier Wochen.

Programme liegen unter `C:\Program Files\PBS-Desk`, Einstellungen, Verlauf und
Zugangsdaten unter `C:\ProgramData\PBS-Desk`.

**Stille Installation** (z.B. per Software-Verteilung):

```powershell
PBS-Desk-Setup-<Version>.exe /VERYSILENT /SUPPRESSMSGBOXES /CONFIG=C:\pfad\pbs-desk.conf
```

`/CONFIG` ist optional und übernimmt eine vorbereitete `pbs-desk.conf`, aber nur,
wenn noch keine Konfiguration existiert. Eine vorhandene Konfiguration bleibt
bei jeder Installation unverändert. Das Token steht nie auf der Befehlszeile
und nie im Setup-Protokoll.

**Deinstallation:** „Installierte Apps“ > PBS-Desk > Deinstallieren, oder still
mit `"C:\Program Files\PBS-Desk\unins000.exe" /VERYSILENT`. Das Programm
entfernt Aufgaben, Autostart und Programmordner. Den Ordner
`C:\ProgramData\PBS-Desk` löscht es nur nach Rückfrage (Vorgabe: behalten);
bei der stillen Deinstallation bleibt er immer erhalten.

**Engine und Lizenz:** Gesichert wird mit `pbsdirectorybackup.exe` (Dateien,
mit VSS) und `pbsmachinebackup.exe` (Disk-Image) aus
[tizbac/proxmoxbackupclient_go](https://github.com/tizbac/proxmoxbackupclient_go),
Version v1.1.3, Lizenz GPL-3.0. Beide liegen unverändert in der Setup-Datei,
nur `pbsdirectorybackup.exe` heißt dort `proxmoxbackup-directory.exe`. Der
Build lädt das Release und prüft es gegen `checksums.txt`. Den Quellcode dieser
Fassung gibt es unter dem Tag
[v1.1.3](https://github.com/tizbac/proxmoxbackupclient_go/tree/v1.1.3), die
Lizenz liegt mit im Programmordner. Details: `windows/installer/THIRD-PARTY.md`.

**Grenzen des Datei-Backups:** Es sichert keine NTFS-ACLs, alternativen
Datenströme (ADS), Dateiattribute und Hardlinks, nur Inhalt, Namen und
Verzeichnisstruktur. Wer sie braucht oder nach einem Plattenausfall ein
startfähiges System will, nimmt das Disk-Image (`windows/IMAGE.md` erklärt das
Zurückspielen auf eine neue SSD). Ohne Setup.exe geht es auch aus dem
entpackten Repo: `powershell -ExecutionPolicy Bypass -File windows\install.ps1`
als Administrator.

## Aufbau

| Pfad                              | Inhalt                                        |
|-----------------------------------|-----------------------------------------------|
| `bin/pbs-backup`                  | Backup-Lauf (Bash), wird vom Timer gestartet  |
| `bin/pbs-tray`                    | Tray und Einstellungsdialog (Python, PySide6) |
| `bin/pbs-settings`                | Root-Helfer für lokale Einstellungen          |
| `bin/pbs-rate`                    | Handschalter für die Drossel                  |
| `bin/pbs-restore`                 | Wiederherstellen und Verlauf (Python, PySide6)|
| `bin/pbs-restore-helper`          | Root-Helfer: Sicherungen auflisten, einhängen |
| `polkit/`                         | Polkit-Regel für den Root-Helfer              |
| `systemd/`                        | Service und Timer                             |
| `config/pbs-backup.conf.example`  | Beispielkonfiguration                         |
| `po/en/`                          | Englische Übersetzung (gettext)               |
| `install.sh`                      | Installieren, Aktualisieren, Entfernen        |

## Wiederherstellen: wie die Rechte verteilt sind

Die Zugangsdaten des Backup-Servers liegen nur für root lesbar unter
`/etc/proxmox-backup-client/`. Die Oberfläche sieht sie nie, sie ruft den
Root-Helfer per `pkexec` (Anmeldung als Administrator, gilt einige Minuten).
Der Helfer hängt die Sicherung mit der Kennung des angemeldeten Benutzers ein.
Damit gelten im eingehängten Baum dieselben Dateirechte wie im laufenden
System: Fremde Home-Verzeichnisse und Systemdateien, die der Benutzer sonst
nicht lesen darf, bleiben auch in der Sicherung zu. Das Token geht über einen
geerbten Dateideskriptor an `proxmox-backup-client` und steht weder in der
Kommandozeile noch in der Umgebung. Der Einhänge-Prozess läuft allerdings
unter der Kennung des Benutzers und hält das Token im Speicher.

## Geplant

1. Pakete als RPM und DEB
2. Ein Programm statt einzelner Skripte, mit Kommandozeile, Oberfläche und Root-Helfer
3. Wiederherstellen für verschlüsselte Sicherungen (Schlüsseldatei)
4. Snapper, zweites Ziel, Sperren und Drossel als abschaltbare Optionen

## Lizenz

GPL-3.0-or-later, siehe `LICENSE`.
