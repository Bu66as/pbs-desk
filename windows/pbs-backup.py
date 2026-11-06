"""PBS-Desk Sicherungslauf unter Windows (Gegenstueck zu bin/pbs-backup).

Laeuft als SYSTEM aus der Aufgabenplanung:
  \\PBS-Desk\\Sicherung       --geplant  (taeglich, Uhrzeiten aus einstellungen.conf)
  \\PBS-Desk\\Sicherung-Hand  --hand     (vom Tray gestartet, umgeht alle Sperren)
  \\PBS-Desk\\Image           --image --geplant  (monatlich, Disk-Image)
  \\PBS-Desk\\Image-Hand      --image --hand     (Tray: "Image jetzt sichern")

Sperren nur fuer geplante Laeufe:
  Arbeitszeit  Mo-Fr WORK_START bis WORK_END (ARBEITSZEIT_SKIP=1)
  Tagessperre  heute schon erfolgreich gesichert (TAGESSPERRE=1)

Gesichert wird QUELLE mit proxmoxbackup-directory, mit VSS-Schattenkopie
(VSS=0 schaltet sie ab). Jeder Lauf haengt eine Zeile an verlauf.jsonl an.

Waehrend des Laufs schreibt er alle 5 s fortschritt.json (Prozent, Restzeit, Bytes, fuer
alle lesbar, ohne Geheimnisse) fuer den Tray und entfernt sie danach wieder.

Mit --image sichert pbsmachinebackup die ganze Systemplatte (IMAGE_DISK, Standard
\\\\.\\PhysicalDrive0, per VSS konsistent) als <id>-image/disk-Image (.img.fidx) fuer
einen Bare-Metal-Restore (EFI, MSR, C:, Recovery). Eigene Backup-ID, damit die
Image-Snapshots nicht zwischen den Datei-Snapshots stehen. Geplante Images laufen nur,
wenn das letzte erfolgreiche Image aelter als IMAGE_TAGE (Standard 28) ist.
"""
import json
import os
import re
import stat
import subprocess
import sys
import threading
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import pbsdesk as p  # noqa: E402



ENGINE_ORDNER = os.path.join(p.DATEN, "engine")

# --- Fortschritt fuer den Tray (wie bin/pbs-backup unter Linux) -----------------
# Prozent = von der Engine verarbeitete Bytes (Summe der "New/Reuse chunk[..] N bytes")
# / vorab gezaehlte Quellgroesse, korrigiert um das Verhaeltnis aus dem letzten Lauf.
# Beim Image zaehlt die Engine selbst mit ("Chunk a/b/..."). Ohne beides: Schaetzung
# aus der Dauer des letzten erfolgreichen Laufs (geschaetzt=true, der Tray schreibt
# "ca."). Vor dem Ende nie ueber 99 %, der Balken laeuft nie rueckwaerts.
FS_TAKT = 5
RUHE_MESSPUNKTE = 6            # ~30 s Messung, bevor eine Restzeit angezeigt wird
CHUNK_DATEI = re.compile(rb"^(?:New|Reuse) chunk\[[0-9a-f]+\] (\d+) bytes")
CHUNK_IMAGE = re.compile(rb"^Chunk (\d+)/(\d+)/")
IMAGE_CHUNK = 4 << 20          # pbsmachinebackup: feste 4-MiB-Chunks (.fidx)
# Liegen nicht in der VSS-Schattenkopie bzw. kann die Engine nicht lesen
NICHT_ZAEHLEN = {"pagefile.sys", "hiberfil.sys", "swapfile.sys", "system volume information"}


def quellgroesse(wurzel):
    """Summe der Dateigroessen unter wurzel, ohne Verknuepfungen/Junctions zu folgen."""
    summe, stapel = 0, [wurzel]
    while stapel:
        try:
            eintraege = os.scandir(stapel.pop())
        except OSError:
            continue
        with eintraege:
            for e in eintraege:
                if e.name.lower() in NICHT_ZAEHLEN:
                    continue
                try:
                    st = e.stat(follow_symlinks=False)
                except OSError:
                    continue
                if stat.S_ISDIR(st.st_mode):
                    if not st.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                        stapel.append(e.path)
                else:
                    summe += st.st_size
    return summe


class Fortschritt:
    """Schreibt waehrend des Laufs alle FS_TAKT s p.FORTSCHRITT (fortschritt.json)."""

    def __init__(self, art, quelle):
        self.image = art == "image"
        self.start = time.time()
        self.bytes = self.chunk = self.chunks = 0
        self.gezaehlt = None
        self.meldungen = self.max = self.prozent = 0
        letzter = next((e for e in reversed(p.verlauf(500))
                        if e.get("art") == art and e.get("status") == "ok"), {})
        self.letzte_dauer = letzter.get("dauer_s") or None
        self.faktor = 1.0
        if letzter.get("gezaehlt_bytes") and letzter.get("verarbeitet_bytes"):
            self.faktor = min(1.5, max(0.5, letzter["verarbeitet_bytes"] / letzter["gezaehlt_bytes"]))
        self.rate = None          # geglaettete Bytes/s fuer die Restzeit
        self.letzt = (self.start, 0)
        self.messpunkte = 0
        self.proc = None          # Engine-Prozess, fuer den Abbruch
        self.abgebrochen = False
        self.fertig = threading.Event()
        if not self.image:
            threading.Thread(target=self._zaehlen, args=(quelle,), daemon=True).start()
        self.faden = threading.Thread(target=self._takt, daemon=True)
        self.faden.start()

    def _zaehlen(self, quelle):
        n = quellgroesse(quelle)
        self.gezaehlt = n or None

    def zeile(self, z):
        """Eine Ausgabezeile der Engine auswerten."""
        m = CHUNK_DATEI.match(z)
        if m:
            self.bytes += int(m.group(1))
            return
        m = CHUNK_IMAGE.match(z)
        if m:
            self.chunk, self.chunks = int(m.group(1)), int(m.group(2))

    def _takt(self):
        while True:
            if os.path.exists(p.ABBRUCH) and not self.abgebrochen:
                self.abgebrochen = True
                if self.proc is not None:
                    try:
                        self.proc.kill()
                    except OSError:
                        pass
            self.messen()
            if self.fertig.wait(FS_TAKT):
                return

    def messen(self):
        dauer = time.time() - self.start
        geschaetzt, rest, gesamt, verarbeitet = False, None, None, self.bytes
        if self.image and self.chunks:
            verarbeitet, gesamt = self.chunk * IMAGE_CHUNK, self.chunks * IMAGE_CHUNK
        elif self.gezaehlt:
            gesamt = int(self.gezaehlt * self.faktor)
        if gesamt and verarbeitet > 0 and dauer > 0:
            prozent = verarbeitet * 100 // gesamt
            # Restzeit aus geglaetteter Rate (EMA ueber die Messpunkte); erst nach
            # RUHE_MESSPUNKTE Messpunkten und 1 % anzeigen, vorher springt sie stark
            jetzt = time.time()
            dt, db = jetzt - self.letzt[0], verarbeitet - self.letzt[1]
            if dt > 0 and db >= 0:
                r = db / dt
                self.rate = r if self.rate is None else 0.8 * self.rate + 0.2 * r
                self.messpunkte += 1
            self.letzt = (jetzt, verarbeitet)
            mittel = verarbeitet / dauer
            rate = max(self.rate or 0, mittel * 0.5)
            if self.messpunkte >= RUHE_MESSPUNKTE and prozent >= 1 and rate > 0:
                rest = int(max(gesamt - verarbeitet, 0) / rate)
        elif self.letzte_dauer:
            geschaetzt = True
            prozent = int(dauer * 100 / self.letzte_dauer)
            rest = int(max(self.letzte_dauer - dauer, 0))
        else:
            geschaetzt, prozent = True, 0
        prozent = max(min(prozent, 99), self.prozent)
        self.prozent = prozent
        d = {"prozent": prozent, "rest_s": rest, "verarbeitet_bytes": verarbeitet,
             "gesamt_bytes": gesamt, "geschaetzt": geschaetzt,
             "start": int(self.start), "stand": int(time.time())}
        tmp = p.FORTSCHRITT + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(d, f)
            # Liest der Tray gerade, verweigert Windows das Ersetzen kurz
            for _ in range(5):
                try:
                    os.replace(tmp, p.FORTSCHRITT)
                    break
                except PermissionError:
                    time.sleep(0.2)
            else:
                return
        except OSError:
            return
        self.meldungen += 1
        self.max = max(self.max, prozent)

    def ende(self):
        """Stoppt die Meldungen, raeumt fortschritt.json weg, liefert Werte fuer den Verlauf."""
        self.fertig.set()
        self.faden.join(10)
        for weg in (p.FORTSCHRITT, p.FORTSCHRITT + ".tmp"):
            try:
                os.remove(weg)
            except OSError:
                pass
        aus = {"fortschritt_meldungen": self.meldungen, "fortschritt_max": self.max}
        if not self.image and self.bytes:
            aus["verarbeitet_bytes"] = self.bytes
            if self.gezaehlt:
                aus["gezaehlt_bytes"] = self.gezaehlt
        return aus


def engine_konfig(werte):
    """Schreibt die Engine-Konfiguration in einen Ordner nur fuer SYSTEM und Administratoren.

    Der Datenordner ist fuer Benutzer lesbar, deshalb ein eigener Unterordner ohne Vererbung.
    Reste abgebrochener Laeufe werden dabei weggeraeumt."""
    os.makedirs(ENGINE_ORDNER, exist_ok=True)
    subprocess.run(["icacls", ENGINE_ORDNER, "/inheritance:r", "/grant:r",
                    "*S-1-5-18:(OI)(CI)F", "*S-1-5-32-544:(OI)(CI)F"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True,
                   creationflags=subprocess.CREATE_NO_WINDOW)
    for alt in os.listdir(ENGINE_ORDNER):
        if alt.startswith("lauf-") and alt.endswith(".json"):
            try:
                os.remove(os.path.join(ENGINE_ORDNER, alt))
            except OSError:
                pass
    pfad = os.path.join(ENGINE_ORDNER, f"lauf-{os.getpid()}.json")
    with open(pfad, "w", encoding="utf-8") as f:
        json.dump(werte, f)
    return pfad

def log(text):
    with open(p.LOG, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {text}\n")


def log_kuerzen(max_bytes=5 << 20):
    try:
        if os.path.getsize(p.LOG) > max_bytes:
            os.replace(p.LOG, p.LOG + ".1")
    except OSError:
        pass


def sperre(w, jetzt):
    if w.get("ARBEITSZEIT_SKIP") == "1" and jetzt.isoweekday() <= 5 \
            and int(w["WORK_START"]) <= jetzt.hour < int(w["WORK_END"]):
        return "Arbeitszeit-Sperre (Mo-Fr {}-{} Uhr)".format(w["WORK_START"], w["WORK_END"])
    if w.get("TAGESSPERRE") == "1":
        d, alter = p.letzter_erfolg()
        if alter == 0:
            return f"Tagessperre: heute schon gesichert ({d:%H:%M})"
    return None


def image_alter():
    """Tage seit dem letzten erfolgreichen Image oder None."""
    e = next((e for e in reversed(p.verlauf(500))
              if e.get("art") == "image" and e.get("status") == "ok"), None)
    try:
        return (datetime.now() - datetime.fromisoformat(e["zeit"])).days if e else None
    except (KeyError, ValueError):
        return None


def abbrechen():
    """Aufgabe \\PBS-Desk\\Abbrechen (SYSTEM, vom Tray ausgeloest): laufende Sicherung beenden."""
    lauf = p.laufender()
    if not lauf:
        return 0
    with open(p.ABBRUCH, "w", encoding="utf-8") as f:
        f.write(datetime.now().isoformat(timespec="seconds"))
    log(f"[{lauf.get('ausloeser', '?')}] ABBRUCH angefordert")
    for _ in range(60):
        if not p.laufender():
            return 0
        time.sleep(0.5)
    # Lauf reagiert nicht: Prozessbaum hart beenden und selbst aufraeumen
    subprocess.run(["taskkill", "/T", "/F", "/PID", str(lauf["pid"])], capture_output=True,
                   creationflags=subprocess.CREATE_NO_WINDOW)
    for weg in (p.LAUF, p.FORTSCHRITT, p.FORTSCHRITT + ".tmp", p.ABBRUCH):
        try:
            os.remove(weg)
        except OSError:
            pass
    p.verlauf_schreiben(lauf.get("art", "backup"), lauf.get("ausloeser", "hand"), "abgebrochen",
                        grund="abgebrochen", meldung="Prozess beendet")
    return 0


def engine_grund(zeilen, verarbeitet):
    """Grund eines Engine-Fehlers aus den letzten Ausgabezeilen."""
    text = b"\n".join(zeilen).decode("utf-8", "replace")
    g = p.fehler_grund(text)
    if g == "unerreichbar" and verarbeitet:
        return "verbindung_weg"
    return g


def main():
    if "--abbrechen" in sys.argv:
        return abbrechen()
    hand = "--hand" in sys.argv
    image = "--image" in sys.argv
    art = "image" if image else "backup"
    ausloeser = "hand" if hand else "geplant"
    os.makedirs(p.DATEN, exist_ok=True)
    log_kuerzen()
    if p.laufender():
        log(f"[{ausloeser}] SKIP: es laeuft schon ein Backup")
        return 0
    w = p.einstellungen()
    jetzt = datetime.now()
    if not hand:
        grund = sperre(w, jetzt) if not image else None
        if image:
            if w.get("ARBEITSZEIT_SKIP") == "1" and jetzt.isoweekday() <= 5 \
                    and int(w["WORK_START"]) <= jetzt.hour < int(w["WORK_END"]):
                grund = "Arbeitszeit-Sperre"
            alter = image_alter()
            if not grund and alter is not None and alter < int(w.get("IMAGE_TAGE") or 28):
                grund = f"letztes Image erst {alter} Tage alt"
        if grund:
            log(f"[geplant] SKIP: {grund}")
            return 0

    c = p.datei_werte(p.CONF)
    fehlt = [k for k in ("PBS_REPOSITORY", "PBS_DATASTORE", "PBS_TOKEN_ID", "PBS_TOKEN_SECRET",
                         "PBS_FINGERPRINT") if not c.get(k)]
    quelle = w.get("QUELLE") or "C:\\"
    backup_id = c.get("PBS_BACKUP_ID") or os.environ.get("COMPUTERNAME", "windows").lower()
    engine = p.ENGINE
    if image:
        quelle = w.get("IMAGE_DISK") or r"\\.\PhysicalDrive0"
        backup_id += "-image"
        engine = p.engine_image()
        if not engine:
            fehlt.append("pbsmachinebackup.exe")
    if fehlt:
        log(f"[{ausloeser}] FEHLER: in pbs-desk.conf fehlt {', '.join(fehlt)}")
        p.verlauf_schreiben(art, ausloeser, "fehler", grund="konfiguration",
                            meldung="Konfiguration unvollständig")
        return 2

    # Vorpruefung mit klarer Ursache (Server weg, Fingerabdruck, Anmeldung), bevor die
    # Engine mit ihren eigenen Meldungen startet
    try:
        p.Server(c).pruefen()
    except Exception as e:  # noqa: BLE001
        grund = p.fehler_grund(e)
        log(f"[{ausloeser}] FEHLER vor dem Start ({grund}): {e}")
        p.verlauf_schreiben(art, ausloeser, "fehler", grund=grund, meldung=str(e)[:200], dauer_s=0)
        return 1

    # Das Token-Secret geht ueber eine JSON-Datei (-config) an die Engine, nie ueber die
    # Befehlszeile: die kann jeder lokale Prozess per Win32_Process.CommandLine lesen.
    vss = w.get("VSS", "1") == "1"
    try:
        konfig = engine_konfig({"secret": c["PBS_TOKEN_SECRET"], "usevss": vss})
    except (OSError, subprocess.CalledProcessError) as e:
        log(f"[{ausloeser}] FEHLER: Engine-Konfiguration nicht schreibbar: {e}")
        p.verlauf_schreiben(art, ausloeser, "fehler", meldung="Engine-Konfiguration")
        return 2
    cmd = [engine, "-config", konfig,
           "-baseurl", c["PBS_REPOSITORY"], "-certfingerprint", c["PBS_FINGERPRINT"],
           "-authid", c["PBS_TOKEN_ID"],
           "-datastore", c["PBS_DATASTORE"], "-backup-id", backup_id]
    # pbsmachinebackup nimmt fuer \\.\PhysicalDriveN selbst eine VSS-Schattenkopie
    cmd += ["-backupdev", quelle] if image else ["-backupdir", quelle]
    if c.get("PBS_NAMESPACE"):
        cmd += ["-namespace", c["PBS_NAMESPACE"]]
    if not vss and not image:
        cmd.append("-novss")

    start = time.time()
    with open(p.LAUF, "w", encoding="utf-8") as f:
        json.dump({"pid": os.getpid(), "start": jetzt.isoformat(timespec="seconds"),
                   "ausloeser": ausloeser, "quelle": quelle, "art": art}, f)
    log(f"[{ausloeser}{'/image' if image else ''}] START {quelle} -> {c['PBS_REPOSITORY']} {c['PBS_DATASTORE']}"
        f"/{c.get('PBS_NAMESPACE', '')} id={backup_id} vss={w.get('VSS', '1')}")
    for weg in (p.ABBRUCH,):
        try:
            os.remove(weg)
        except OSError:
            pass
    fs = Fortschritt(art, quelle)
    letzte = []
    try:
        with open(p.LOG, "ab") as logf:
            # Geheimnis steht nur in der Engine-Konfiguration, nie in Befehlszeile oder Protokoll.
            # Ausgabe zeilenweise ins Protokoll und an die Fortschrittsmessung.
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    creationflags=subprocess.CREATE_NO_WINDOW)
            fs.proc = proc
            if fs.abgebrochen:
                proc.kill()
            for z in proc.stdout:
                logf.write(z)
                fs.zeile(z)
                if not z.startswith((b"New chunk", b"Reuse chunk", b"Chunk ")):
                    letzte = (letzte + [z.strip()])[-40:]
            rc = proc.wait()
    except OSError as e:
        log(f"[{ausloeser}] FEHLER: {e}")
        rc = -1
    finally:
        fs_werte = fs.ende()
        for weg in (p.LAUF, konfig, p.ABBRUCH):
            try:
                os.remove(weg)
            except OSError:
                pass
    dauer = int(time.time() - start)
    status = "ok" if rc == 0 else "fehler"
    mehr = {}
    if fs.abgebrochen:
        status, mehr = "abgebrochen", {"grund": "abgebrochen"}
    elif rc != 0:
        mehr = {"grund": engine_grund(letzte, fs.bytes),
                "meldung": (letzte[-1] if letzte else b"").decode("utf-8", "replace")[:200]}
    log(f"[{ausloeser}{'/image' if image else ''}] ENDE rc={rc} status={status} dauer={dauer}s "
        f"fortschritt_meldungen={fs_werte['fortschritt_meldungen']} max={fs_werte['fortschritt_max']}")
    p.verlauf_schreiben(art, ausloeser, status, dauer_s=dauer, rc=rc, quelle=quelle,
                        ziel=f"{c['PBS_REPOSITORY']}/{c['PBS_DATASTORE']}/{c.get('PBS_NAMESPACE', '')}",
                        backup_id=backup_id, **fs_werte, **mehr)
    return 0 if status == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
