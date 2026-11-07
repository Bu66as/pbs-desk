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
# Abbruchwunsch: legt pbs-backup.py --abbrechen (Aufgabe \PBS-Desk\Abbrechen) an
ABBRUCH = os.path.join(DATEN, "abbrechen")
AUFGABE_ABBRECHEN = r"\PBS-Desk\Abbrechen"
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


def eingerichtet():
    """Ist ein Backup-Server eingetragen? Der Tray darf pbs-desk.conf nicht lesen,
    deshalb vermerken Setup und Einstellungen das in einstellungen.conf (EINGERICHTET).
    Fehlt der Vermerk (aeltere Installation), gilt die Einrichtung als vorhanden."""
    return datei_werte(EINSTELLUNGEN).get("EINGERICHTET", "1") != "0"


def zeit_text(d):
    """'heute 14:02', 'gestern 09:10' oder '03.11. 18:00'."""
    tage = (date.today() - d.date()).days
    uhr = d.strftime("%H:%M")
    if tage == 0:
        return _("heute {uhr}").format(uhr=uhr)
    if tage == 1:
        return _("gestern {uhr}").format(uhr=uhr)
    return d.strftime(_("%d.%m.")) + " " + uhr


def zeit_text_kuenftig(d):
    """'heute 18:00', 'morgen 07:30' oder '09.11. 07:30'."""
    tage = (d.date() - date.today()).days
    uhr = d.strftime("%H:%M")
    if tage == 0:
        return _("heute {uhr}").format(uhr=uhr)
    if tage == 1:
        return _("morgen {uhr}").format(uhr=uhr)
    return d.strftime(_("%d.%m.")) + " " + uhr


def letzter_lauf(art="backup"):
    return next((e for e in reversed(verlauf()) if e.get("art") == art
                 and e.get("status") in ("ok", "fehler", "abgebrochen")), None)


def status_zeile():
    """Erste Zeile von Tray-Menue und Tooltip in Klartext (ohne laufende Sicherung)."""
    if not eingerichtet():
        return _("Noch nicht eingerichtet – bitte „Einstellungen …“ öffnen")
    e = letzter_lauf()
    if e is None:
        return _("Noch keine Sicherung")
    if e.get("status") == "abgebrochen":
        return _("Letzte Sicherung: Abgebrochen ✗")
    if e.get("status") == "fehler":
        return _("Letzte Sicherung fehlgeschlagen ✗ – Verlauf ansehen")
    try:
        d = datetime.fromisoformat(e["zeit"]).replace(tzinfo=None)
    except (KeyError, ValueError):
        return _("Noch keine Sicherung")
    return _("Letzte Sicherung: {zeit} ✓").format(zeit=zeit_text(d))


def naechster_termin(w=None, jetzt=None):
    """Naechste geplante Uhrzeit als datetime (ohne Sperren) oder None."""
    from datetime import timedelta
    w = w or einstellungen()
    jetzt = jetzt or datetime.now()
    kandidaten = []
    for t in w.get("UHRZEITEN", "").split(","):
        try:
            h, m = (int(x) for x in t.strip().split(":"))
        except ValueError:
            continue
        for tag in range(0, 3):
            d = (jetzt + timedelta(days=tag)).replace(hour=h, minute=m, second=0, microsecond=0)
            if d > jetzt:
                kandidaten.append(d)
                break
    return min(kandidaten) if kandidaten else None


# Klartext fuer Fehlergruende (gleiche Texte wie unter Linux)
GRUENDE = {
    "anmeldung": lambda: _("Anmeldung abgelehnt: API-Token oder Token-Geheimnis stimmt nicht. "
                           "Bitte beide Felder prüfen."),
    "fingerabdruck": lambda: _("Der Server meldet einen anderen Fingerabdruck als eingetragen. "
                               "Mit „Vom Server holen“ neu abrufen und mit dem Dashboard "
                               "vergleichen."),
    "unerreichbar": lambda: _("Server nicht erreichbar. Bitte Netzwerkverbindung und "
                              "Serveradresse prüfen."),
    "verbindung_weg": lambda: _("Die Verbindung zum Backup-Server ist während der Sicherung "
                                "abgebrochen. Der nächste Lauf startet automatisch."),
    "abgebrochen": lambda: _("Von Hand abgebrochen. Die Sicherung ist unvollständig."),
    "konfiguration": lambda: _("Die Verbindung zum Backup-Server ist nicht vollständig eingerichtet."),
    "sonstiges": lambda: _("Die Sicherung ist fehlgeschlagen. Einzelheiten stehen im technischen Protokoll."),
}


def grund_text(grund):
    return GRUENDE.get(grund, GRUENDE["sonstiges"])()


def fehler_grund(fehler):
    """Ordnet eine Ausnahme oder einen Engine-Text einem Grund aus GRUENDE zu."""
    t = str(fehler).lower()
    if isinstance(fehler, FingerabdruckFehler) or "fingerprint" in t or "fingerabdruck" in t \
            or "x509" in t or "certificate" in t:
        return "fingerabdruck"
    if isinstance(fehler, AnmeldungFehler) or "401" in t or "unauthorized" in t \
            or "authentication fail" in t or "permission check failed" in t or "403" in t:
        return "anmeldung"
    if isinstance(fehler, (socket.timeout, TimeoutError, ConnectionError, socket.gaierror)) \
            or any(w in t for w in ("timed out", "timeout", "refused", "unreachable", "no route",
                                    "dial tcp", "connectex", "getaddrinfo", "no such host",
                                    "nicht erreichbar", "wsarecv", "wsasend", "forcibly closed",
                                    "connection reset", "broken pipe", "eof", "connection lost")):
        return "unerreichbar"
    return "sonstiges"


def klartext(fehler):
    return grund_text(fehler_grund(fehler))


class FingerabdruckFehler(ssl.SSLError):
    pass


class AnmeldungFehler(OSError):
    pass


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
            raise FingerabdruckFehler(_("Fingerabdruck des Servers stimmt nicht."))
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
            if r.status in (401, 403):
                raise AnmeldungFehler(f"HTTP {r.status}")
            if r.status != 200:
                raise OSError(f"HTTP {r.status}: {roh[:200].decode('utf-8', 'replace')}")
            return json.loads(roh)["data"]
        finally:
            v.close()

    def pruefen(self, timeout=15):
        """Erreichbarkeit, Fingerabdruck und Anmeldung pruefen (wirft bei Fehler)."""
        v = self._verbindung(timeout=timeout)
        try:
            v.request("GET", f"/api2/json/admin/datastore/{self.store}/groups?"
                      + urllib.parse.urlencode({"ns": self.ns} if self.ns else {}),
                      headers={"Authorization": self.auth})
            r = v.getresponse()
            r.read()
            if r.status in (401, 403):
                raise AnmeldungFehler(f"HTTP {r.status}")
            if r.status != 200:
                raise OSError(f"HTTP {r.status}")
        finally:
            v.close()

    def snapshots(self, nur_fertige=False):
        s = self.json("snapshots", ns=self.ns)
        if nur_fertige:
            # Laufende Sicherungen stehen schon in der Liste, haben aber noch keinen
            # Katalog: deren Katalogabfrage scheitert
            s = [x for x in s if any(f.get("filename", "").startswith("catalog.")
                                     for f in x.get("files", []))
                 and any(f.get("filename", "").endswith(".pxar.didx") for f in x.get("files", []))]
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
