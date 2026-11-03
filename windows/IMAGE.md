# PBS-Desk Windows: Disk-Image (Bare-Metal) und NTFS-Rechte

Das normale PBS-Desk-Backup unter Windows sichert **Dateien** von `C:\` (VSS-Schattenkopie,
`proxmoxbackup-directory`, Archiv `*.pxar`). Damit lassen sich Dateien zurückholen, aber
kein lauffähiges System auf eine leere SSD bringen: EFI-Systempartition, MSR und
Recovery-Partition fehlen, und die Datei-Sicherung behält die NTFS-Metadaten nicht (siehe unten).

Dafür gibt es zusätzlich das **Disk-Image**: `pbsmachinebackup` liest die ganze Systemplatte
(`\\.\PhysicalDrive0`, per VSS konsistent) und legt sie als Fixed-Index-Archiv
(`drive-sata0.img.fidx`, 4-MiB-Chunks) auf dem PBS ab.

## Wann läuft das Image?

| Auslöser                    | Aufgabe                | Verhalten                                                    |
|-----------------------------|------------------------|--------------------------------------------------------------|
| Tray „Image jetzt sichern …“ | `\PBS-Desk\Image-Hand` | sofort, ohne Sperren (vor Treiber-/Windows-Updates u. ä.)     |
| Plan                        | `\PBS-Desk\Image`      | samstags alle 4 Wochen zur ersten Backup-Uhrzeit, holt verpasste Läufe nach; läuft nur, wenn das letzte erfolgreiche Image älter als `IMAGE_TAGE` (Standard 28) ist; beachtet die Arbeitszeit-Sperre |

Begründung: Ein Image ist groß (ganze Disk, z. B. 128 GB, davon 72 GB belegt) und
dauert über WLAN eine bis mehrere Stunden. Die täglichen Datei-Backups decken die Daten ab.
Das Image braucht man nur für den Totalausfall der SSD. Dafür reicht ein Stand, der höchstens
einen Monat alt ist, plus ein Image von Hand vor riskanten Änderungen am System. Läuft gerade ein Backup, startet kein zweites (gemeinsame `laeuft.json`).

Einstellungen in `C:\ProgramData\PBS-Desk\einstellungen.conf` (optional):

```
IMAGE_DISK=\\.\PhysicalDrive0
IMAGE_TAGE=28
```

Ziel ist derselbe PBS/Datastore/Namespace wie beim Datei-Backup, aber mit eigener Backup-ID
`<gerät>-image` (z. B. `host/mein-pc-image`), damit die Image-Snapshots nicht zwischen
den Datei-Snapshots im Wiederherstellen-Dialog auftauchen. Das Token-Secret geht wie beim
Datei-Backup über die `-config`-Datei an die Engine, nie über die Befehlszeile.

Engine: `C:\Program Files\PBS-Desk\bin\pbsmachinebackup.exe`, ersatzweise
`C:\ProgramData\PBS-Desk\engine\x\pbsmachinebackup.exe` (aus demselben Release wie
`proxmoxbackup-directory`). Fehlt beides, blendet der Tray den Menüpunkt aus.

## Image auf eine neue SSD zurückspielen

Grundsatz: Das Image wird **von einem Linux-Live-System aus** Block für Block auf die neue SSD
geschrieben. Windows selbst braucht dafür nichts.

### Was man braucht

- Neue SSD, **mindestens so groß wie die alte** (Größe in Byte vorher notieren).
- USB-Stick mit einem Linux-Live-System, auf dem `proxmox-backup-client` läuft, z. B.
  Debian 13 Live (`debian-live-13-amd64-standard.iso`)
  Mit Rufus oder `dd` auf den Stick schreiben.
- Netz zum PBS (`<pbs-host>:8007`), am besten per Kabel (USB-LAN-Adapter), weil das
  Zurückspielen sonst so langsam ist wie die Sicherung über WLAN.
- Zugang: API-Token des Geräts (Token-ID und Secret aus dem Passwortmanager bzw.
  `C:\ProgramData\PBS-Desk\pbs-desk.conf` der alten Installation) und der Fingerprint des PBS.

### Schritte

1. Neue SSD einbauen, vom USB-Stick booten (Boot-Menü-Taste je nach Hersteller; Secure Boot kann für Debian an bleiben).
2. Client installieren (Debian Live, als root):

   ```bash
   echo "deb http://download.proxmox.com/debian/pbs-client trixie main" \
     > /etc/apt/sources.list.d/pbs-client.list
   wget -qO /etc/apt/trusted.gpg.d/proxmox-release-trixie.gpg \
     https://enterprise.proxmox.com/debian/proxmox-release-trixie.gpg
   apt update && apt install -y proxmox-backup-client gdisk
   ```

3. Zugang setzen (Secret nicht in die History tippen: `read -rs`):

   ```bash
   export PBS_REPOSITORY='<token-id>@<pbs-host>:8007:<datastore>'
   export PBS_FINGERPRINT='<fingerprint>'
   read -rs PBS_PASSWORD && export PBS_PASSWORD
   NS=<namespace>
   proxmox-backup-client snapshot list --ns $NS | grep -- -image
   ```

4. Ziel-SSD **eindeutig** bestimmen (Größe/Modell prüfen, der USB-Stick darf es nicht sein):

   ```bash
   lsblk -d -o NAME,SIZE,MODEL,TRAN
   ```

5. Image schreiben (Beispiel `/dev/sda`, Snapshot-Zeit aus Schritt 3):

   ```bash
   proxmox-backup-client restore --ns $NS \
     host/<gerät>-image/<snapshot-zeit> drive-sata0.img - \
     | dd of=/dev/sda bs=4M iflag=fullblock oflag=direct conv=fsync status=progress
   ```

6. GPT prüfen und bei größerer SSD die Backup-GPT ans Plattenende verschieben:

   ```bash
   sgdisk -e /dev/sda      # nur nötig, wenn die neue SSD größer ist
   sgdisk -v /dev/sda && sgdisk -p /dev/sda
   ```

   Erwartet: 4 Partitionen: EFI-System (FAT32), Microsoft reserved,
   Basic data (C:), Windows Recovery.

7. Stick abziehen, neu starten. Startet der Rechner nicht von der SSD, im BIOS den
   UEFI-Booteintrag „Windows Boot Manager“ neu anlegen (Datei
   `\EFI\Microsoft\Boot\bootmgfw.efi`). Falls das nicht hilft: Windows-Installations-Stick →
   Computerreparaturoptionen → Eingabeaufforderung → `bcdboot C:\Windows /f UEFI`.
8. In Windows ggf. C: in der Datenträgerverwaltung vergrößern (Recovery-Partition liegt
   dahinter, also erst verschieben oder belassen). Danach ein normales PBS-Desk-Backup
   und ein neues Image anstoßen.

Hinweise:
- Ist BitLocker aktiv, braucht Windows nach dem
  Rückspielen auf neue Hardware den Wiederherstellungsschlüssel.
- Ohne neue SSD lässt sich das Image auch testweise prüfen oder als VM starten:
  `proxmox-backup-client map … drive-sata0.img` liefert ein Loop-Device (`/dev/loopN`), das man
  nur lesend einhängen kann. Alternativ das Image auf einem PVE-Host in eine VM-Disk schreiben
  (UEFI/OVMF, SATA).
- Einzelne Dateien holt man weiterhin aus dem Datei-Backup (Tray → Wiederherstellen), nicht aus dem Image.

## Was sichert das Datei-Backup von NTFS? (geprüft)

Kurz: **Nein.** Das Datei-Backup (`proxmoxbackup-directory`, pxar) sichert nur Inhalt,
Name und Verzeichnisstruktur. NTFS-Rechte, Attribute, alternative Datenströme und Hardlinks
gehen verloren. Wer sie braucht, nimmt das Disk-Image, denn das enthält das NTFS-Dateisystem
bitgenau und damit auch alle Metadaten.

Test an einem Windows-11-Gerät mit einem echten Testordner `C:\ProgramData\PBS-Desk\ntfs-test`:

| Testobjekt                                  | Angelegt mit                                   | Nach der Rücksicherung                        |
|---------------------------------------------|------------------------------------------------|-----------------------------------------------|
| `datei.txt` mit zusätzlicher ACE (Gäste: R) | `icacls … /grant *S-1-5-32-546:(R)`            | Inhalt ok, **keine ACL** (kein xattr, Modus 777) |
| ADS `datei.txt:geheim`                      | `Set-Content -Stream geheim "ADS-Inhalt-4711"` | **fehlt** (Text nirgends im Archiv)            |
| `versteckt.txt` versteckt + schreibgeschützt | `attrib +h +r`                                | Inhalt ok, **Attribute weg** (Modus 777)       |
| `hardlink.txt` → Hardlink auf `datei.txt`   | `New-Item -ItemType HardLink`                  | **eigene Kopie** (Linkzahl 1, 13 Byte doppelt) |

Vorgehen: Ordner mit der Engine gesichert (eigene Backup-ID, ohne VSS),
Ordner danach wieder gelöscht, Snapshot auf dem PBS mit `proxmox-backup-client
restore` nach `/tmp` zurückgeholt und mit `find -printf` (Linkzahl, Modus) und
`os.listxattr` geprüft. Das pxar-Format könnte ACLs als xattrs, Hardlinks und Dateimodi
tragen, aber die Windows-Engine schreibt sie nicht. Die PBS-Desk-Wiederherstellung unter
Windows lädt Dateien über die PBS-API herunter und setzt daher ohnehin nur den Inhalt;
zurückgeholte Dateien erben die Rechte des Zielordners.

Folgen für die Praxis:
- Benutzerdaten (Dokumente, Exporte) aus dem Datei-Backup holen: unkritisch.
- Programm- oder Systemordner mit besonderen Rechten (`C:\Program Files`, `C:\Windows`,
  Dienstkonten) nicht aus dem Datei-Backup zurückkopieren, sondern das Image nehmen.
- Hardlinks (z. B. im WinSxS-Speicher) werden beim Datei-Backup mehrfach gesichert. Durch
  die Deduplizierung auf dem PBS kostet das kaum Platz.

