"""Gemeinsame Teile von PBS-Desk unter Windows.

Pfade, Sprache, Einstellungen, Verlauf und der Zugriff auf den Backup-Server.
Entspricht unter Linux den verstreuten Konstanten in pbs-tray/pbs-settings/
pbs-backup: statt /etc und /var/lib liegt alles unter C:\\ProgramData\\PBS-Desk,
die Programme unter C:\\Program Files\\PBS-Desk.
"""
import base64
import ctypes
import gettext
import hashlib
import http.client
import json
import os
import socket
import ssl
import subprocess
import urllib.parse
from datetime import date, datetime

PROGRAMM = "PBS-Desk"
PROG = os.environ.get("PBS_DESK_HOME", r"C:\Program Files\PBS-Desk")
DATEN = os.environ.get("PBS_DESK_DATEN", r"C:\ProgramData\PBS-Desk")
APP = os.path.dirname(os.path.realpath(__file__))
PYTHONW = os.path.join(PROG, "python", "pythonw.exe")
PYTHON = os.path.join(PROG, "python", "python.exe")
ENGINE = os.path.join(PROG, "bin", "proxmoxbackup-directory.exe")
# Disk-Image (Bare-Metal): pbsmachinebackup aus demselben Engine-Paket
ENGINE_IMAGE_KANDIDATEN = (os.path.join(PROG, "bin", "pbsmachinebackup.exe"),
                           os.path.join(DATEN, "engine", "x", "pbsmachinebackup.exe"))
SYMBOL_ORDNER = os.path.join(PROG, "icons")
LOCALEDIR = os.path.join(PROG, "locale")

# Zugangsdaten: nur SYSTEM und Administratoren (wie /etc/proxmox-backup-client/lokal)
CONF = os.path.join(DATEN, "pbs-desk.conf")
# Uhrzeiten, Sperren, Quelle: fuer alle lesbar, damit der Tray sie anzeigen kann
EINSTELLUNGEN = os.path.join(DATEN, "einstellungen.conf")
VERLAUF = os.path.join(DATEN, "verlauf.jsonl")
LAUF = os.path.join(DATEN, "laeuft.json")
LOG = os.path.join(DATEN, "backup.log")
# Fortschritt des laufenden Backups, von pbs-backup.py geschrieben, vom Tray gelesen
FORTSCHRITT = os.path.join(DATEN, "fortschritt.json")
AUFGABE = r"\PBS-Desk\Sicherung"
AUFGABE_HAND = r"\PBS-Desk\Sicherung-Hand"
AUFGABE_IMAGE = r"\PBS-Desk\Image"
AUFGABE_IMAGE_HAND = r"\PBS-Desk\Image-Hand"


def engine_image():
    return next((e for e in ENGINE_IMAGE_KANDIDATEN if os.path.isfile(e)), None)

STANDARD = {
    "UHRZEITEN": "07:30,12:30,18:00",
    "ARBEITSZEIT_SKIP": "1", "WORK_START": "8", "WORK_END": "17",
    "TAGESSPERRE": "1",
    "QUELLE": "C:\\",
    "VSS": "1",
    "STALE_DAYS": "3",
}
SERVER_SCHLUESSEL = ("PBS_REPOSITORY", "PBS_DATASTORE", "PBS_NAMESPACE", "PBS_BACKUP_ID",
                     "PBS_TOKEN_ID", "PBS_FINGERPRINT")


# --- Sprache ---------------------------------------------------------------
def sprache_deutsch():
    """Deutsch, wenn die Anzeigesprache von Windows Deutsch ist; sonst Englisch."""
    w = os.environ.get("PBS_DESK_LANG", "")
    if w:
        return w.lower().startswith("de")
    try:
        return (ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF) == 0x07
    except Exception:
        return False


_ = (gettext.NullTranslations() if sprache_deutsch() else
     gettext.translation("pbs-desk", LOCALEDIR, languages=["en"], fallback=True)).gettext


def qt_uebersetzen(app):
    """Qt-Standardknoepfe (OK, Abbrechen …) in der passenden Sprache."""
    from PySide6.QtCore import QLibraryInfo, QTranslator
    t = QTranslator(app)
    if t.load("qtbase_" + ("de" if sprache_deutsch() else "en"),
              QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
        app.installTranslator(t)
    app._pbs_tr = t


def symbol(name):
    from PySide6.QtGui import QIcon
    return QIcon(os.path.join(SYMBOL_ORDNER, name + ".svg"))


# --- Dateien ---------------------------------------------------------------
def datei_werte(pfad):
    w = {}
    try:
        with open(pfad, encoding="utf-8-sig") as f:
            for z in f:
                z = z.strip()
                if z and not z.startswith("#") and "=" in z:
                    k, v = z.split("=", 1)
                    w[k.strip()] = v.strip()
    except OSError:
        pass
    return w


def datei_schreiben(pfad, werte, kopf):
    tmp = pfad + ".neu"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(kopf + "\n")
        for k, v in werte.items():
            f.write(f"{k}={v}\n")
    os.replace(tmp, pfad)


def einstellungen():
    w = dict(STANDARD)
    w.update(datei_werte(EINSTELLUNGEN))
    return w


def ist_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def erhoeht_starten(skript, *args):
    """Startet ein Werkzeug mit Administratorrechten (UAC statt pkexec)."""
    param = subprocess.list2cmdline([os.path.join(APP, skript), *args])
    r = ctypes.windll.shell32.ShellExecuteW(None, "runas", PYTHONW, param, APP, 1)
    return r > 32


# --- Verlauf und Lauf --------------------------------------------------------
def verlauf_schreiben(art, ausloeser, status, **mehr):
    eintrag = {"zeit": datetime.now().astimezone().isoformat(timespec="seconds"),
               "art": art, "ausloeser": ausloeser, "status": status}
    eintrag.update(mehr)
    with open(VERLAUF, "a", encoding="utf-8") as f:
        f.write(json.dumps(eintrag, ensure_ascii=False) + "\n")


def verlauf(n=200):
    try:
        # utf-8-sig: mit PowerShell 5.1 bearbeitete Dateien beginnen mit BOM
        with open(VERLAUF, encoding="utf-8-sig") as f:
            zeilen = f.readlines()[-n:]
    except OSError:
        return []
    aus = []
    for z in zeilen:
        try:
            aus.append(json.loads(z))
        except ValueError:
            pass
    return aus


def letzter_erfolg():
    """(datetime, Alter in Tagen) der letzten erfolgreichen Sicherung oder (None, None)."""
    for e in reversed(verlauf()):
        if e.get("art") == "backup" and e.get("status") == "ok":
            try:
                d = datetime.fromisoformat(e["zeit"]).replace(tzinfo=None)
            except (KeyError, ValueError):
                continue
            return d, (date.today() - d.date()).days
    return None, None


def prozess_lebt(pid):
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    k = ctypes.windll.kernel32
    h = k.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not h:
        # Zugriff verweigert heisst: es gibt ihn (ERROR_ACCESS_DENIED = 5)
        return k.GetLastError() == 5
    code = ctypes.c_ulong()
    k.GetExitCodeProcess(h, ctypes.byref(code))
    k.CloseHandle(h)
    return code.value == 259  # STILL_ACTIVE


def laufender():
    """Daten des laufenden Backups oder None."""
    try:
        with open(LAUF, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return None
    return d if prozess_lebt(d.get("pid", 0)) else None


def letzte_logzeile():
    try:
        with open(LOG, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 4096))
            zeilen = [z.strip() for z in f.read().decode("utf-8", "replace").splitlines() if z.strip()]
        return zeilen[-1][-90:] if zeilen else None
    except OSError:
        return None


# --- Backup-Server -----------------------------------------------------------
def fp_norm(fp):
    return fp.replace(":", "").strip().lower()


def fingerabdruck(host, port, timeout=8):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with socket.create_connection((host, int(port)), timeout=timeout) as s:
        with ctx.wrap_socket(s, server_hostname=host) as t:
            h = hashlib.sha256(t.getpeercert(binary_form=True)).hexdigest()
    return ":".join(h[i:i + 2] for i in range(0, len(h), 2))


class Server:
    """Kleiner Client fuer die PBS-API mit Token und festgenagelten Fingerabdruck."""

    def __init__(self, conf=None, geheimnis=None):
        c = conf if conf is not None else datei_werte(CONF)
        u = urllib.parse.urlparse(c.get("PBS_REPOSITORY", ""))
        if not u.hostname:
            raise ValueError(_("Kein Backup-Server eingetragen."))
        self.host, self.port = u.hostname, u.port or 8007
        self.store = c.get("PBS_DATASTORE", "")
        self.ns = c.get("PBS_NAMESPACE", "")
        self.fp = fp_norm(c.get("PBS_FINGERPRINT", ""))
        self.auth = f"PBSAPIToken={c.get('PBS_TOKEN_ID', '')}:{geheimnis or c.get('PBS_TOKEN_SECRET', '')}"

    def _verbindung(self, timeout=30):
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        v = http.client.HTTPSConnection(self.host, self.port, context=ctx, timeout=timeout)
        v.connect()
        echt = hashlib.sha256(v.sock.getpeercert(binary_form=True)).hexdigest()
        if self.fp and echt != self.fp:
            v.close()
            raise ssl.SSLError(_("Fingerabdruck des Servers stimmt nicht."))
        return v

    def anfrage(self, pfad, **params):
        params = {k.replace("_", "-"): v for k, v in params.items() if v not in (None, "")}
        v = self._verbindung()
        v.request("GET", f"/api2/json/admin/datastore/{self.store}/{pfad}?"
                  + urllib.parse.urlencode(params), headers={"Authorization": self.auth})
        return v, v.getresponse()

    def json(self, pfad, **params):
        v, r = self.anfrage(pfad, **params)
        try:
            roh = r.read()
            if r.status != 200:
                raise OSError(f"HTTP {r.status}: {roh[:200].decode('utf-8', 'replace')}")
            return json.loads(roh)["data"]
        finally:
            v.close()

    def snapshots(self):
        s = self.json("snapshots", ns=self.ns)
        return sorted(s, key=lambda x: x.get("backup-time", 0), reverse=True)

    def katalog(self, snap, pfad):
        return self.json("catalog", ns=self.ns, backup_type=snap["backup-type"],
                         backup_id=snap["backup-id"], backup_time=snap["backup-time"],
                         filepath=base64.b64encode(pfad.encode()).decode())

    def herunterladen(self, snap, pfad, ziel_datei):
        """Laedt Datei (roh) oder Verzeichnis (zip) nach ziel_datei."""
        v, r = self.anfrage("pxar-file-download", ns=self.ns, backup_type=snap["backup-type"],
                            backup_id=snap["backup-id"], backup_time=snap["backup-time"],
                            filepath=base64.b64encode(pfad.encode()).decode())
        try:
            if r.status != 200:
                raise OSError(f"HTTP {r.status}: {r.read()[:200].decode('utf-8', 'replace')}")
            with open(ziel_datei, "wb") as f:
                while True:
                    b = r.read(1 << 20)
                    if not b:
                        break
                    f.write(b)
        finally:
            v.close()
