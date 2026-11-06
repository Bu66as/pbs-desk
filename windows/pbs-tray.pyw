"""PBS-Desk Tray unter Windows (Gegenstueck zu bin/pbs-tray).

Zeigt im Infobereich der Taskleiste, ob gerade gesichert wird und wie alt die
letzte erfolgreiche Sicherung ist. Gleiche Symbole und Texte wie unter Linux.
Waehrend eines Laufs Prozent und Restzeit aus fortschritt.json (schreibt pbs-backup.py).
Ein Start von Hand laeuft ueber die Aufgabe \\PBS-Desk\\Sicherung-Hand (als SYSTEM,
ohne Rueckfrage und ohne Arbeitszeit-/Tagessperre). Einstellungen und
Wiederherstellen fragen ueber UAC nach Administratorrechten.
"""
import json
import os
import subprocess
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import pbsdesk as p  # noqa: E402
from pbsdesk import _  # noqa: E402

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtGui import QAction  # noqa: E402
from PySide6.QtWidgets import (QApplication, QDialog, QDialogButtonBox, QHBoxLayout,  # noqa: E402
                               QHeaderView, QLabel, QMenu, QMessageBox, QPushButton,
                               QSystemTrayIcon, QTableWidget, QTableWidgetItem, QVBoxLayout)


def geraet():
    return os.environ.get("COMPUTERNAME", "").lower()


def titel():
    return _("{programm} – Backup {geraet}").format(programm=p.PROGRAMM, geraet=geraet())


def herunterfahren():
    try:
        subprocess.run(["shutdown", "/s", "/t", "0"], creationflags=subprocess.CREATE_NO_WINDOW,
                       check=True, timeout=20)
        return True
    except Exception:
        return False


def fortschritt_daten():
    """Prozent und Restzeit des laufenden Backups aus fortschritt.json.

    pbs-backup.py (SYSTEM) schreibt die Datei alle 5 s und entfernt sie nach dem
    Lauf. Mehr als 99 % zeigt der Tray vor dem Ende nie an.
    """
    try:
        with open(p.FORTSCHRITT, encoding="utf-8") as f:
            d = json.load(f)
        prozent = max(0, min(int(d["prozent"]), 99))
    except (OSError, ValueError, TypeError, KeyError):
        return None
    rest = d.get("rest_s")
    return {"prozent": prozent,
            "rest_s": int(rest) if isinstance(rest, (int, float)) and rest >= 0 else None,
            "geschaetzt": d.get("geschaetzt") is True}


def restzeit(sekunden):
    minuten = max(1, (sekunden + 59) // 60)
    if minuten < 60:
        return _("{m} min").format(m=minuten)
    return _("{h} h {m} min").format(h=minuten // 60, m=minuten % 60)


def prozent_text(d):
    if d["geschaetzt"]:
        return _("ca. {prozent} %").format(prozent=d["prozent"])
    return _("{prozent} %").format(prozent=d["prozent"])


def fortschritt_zeile(d):
    """z.B. 'Sicherung läuft: 42 % – noch ca. 12 min'."""
    if d["prozent"] >= 99:
        # Engine schreibt Index und Katalog: keine Restzeit mehr, kein "haengt bei 99 %"
        return _("Sicherung wird abgeschlossen …")
    if d["rest_s"] is None:
        return _("Sicherung läuft: {prozent}").format(prozent=prozent_text(d))
    return _("Sicherung läuft: {prozent} – noch ca. {rest}").format(
        prozent=prozent_text(d), rest=restzeit(d["rest_s"]))


def balken(prozent, breite=16):
    voll = prozent * breite // 100
    return "█" * voll + "░" * (breite - voll)


class AbschaltDialog(QDialog):
    SEKUNDEN = 60

    def __init__(self):
        super().__init__()
        self.setWindowTitle(p.PROGRAMM)
        self.setWindowIcon(p.symbol("pbs-desk"))
        self.rest = self.SEKUNDEN
        lay = QVBoxLayout(self)
        self.text = QLabel()
        lay.addWidget(self.text)
        knoepfe = QDialogButtonBox()
        knoepfe.addButton(_("Jetzt herunterfahren"), QDialogButtonBox.ButtonRole.AcceptRole)
        knoepfe.addButton(QDialogButtonBox.StandardButton.Cancel)
        knoepfe.accepted.connect(self.accept)
        knoepfe.rejected.connect(self.reject)
        lay.addWidget(knoepfe)
        self.uhr = QTimer(self)
        self.uhr.timeout.connect(self.ticken)
        self.uhr.start(1000)
        self.ticken(anzeigen_nur=True)

    def ticken(self, anzeigen_nur=False):
        if not anzeigen_nur:
            self.rest -= 1
        if self.rest <= 0:
            self.accept()
            return
        self.text.setText(_("Backup fertig. Der Rechner fährt in {s} Sekunden herunter.").format(s=self.rest))


class Tray(QSystemTrayIcon):
    def __init__(self):
        super().__init__()
        self.menu = QMenu()
        self.setContextMenu(self.menu)
        self.menu.aboutToShow.connect(self.menue_bauen)
        self.activated.connect(self.geklickt)
        self._abschalten = None      # Zeitpunkt, ab dem auf das Laufende gewartet wird
        self._aktiv = False
        self._balken = self._kopf_aktion = None
        self._seit = ""
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.aktualisieren)
        self.aktualisieren()
        self.timer.start()
        self.show()
        self._erststart_versuche = 0
        QTimer.singleShot(3000, self.erststart)

    # --- Anzeige ---------------------------------------------------------
    def aktualisieren(self):
        lauf = p.laufender()
        aktiv = lauf is not None
        d, alter = p.letzter_erfolg()
        stale = int(p.einstellungen().get("STALE_DAYS", "3"))
        if aktiv:
            icon, kopf = "pbs-desk-laeuft", _("Backup läuft gerade")
            # Keine rohe Logzeile: Chunk-Hashes fuellen sonst die 127 Zeichen und
            # schneiden den Hinweis ab. Beginn und Ausloeser reichen.
            seit = (lauf.get("start") or "")[11:16]
            art = _("von Hand") if lauf.get("ausloeser") == "hand" else _("geplant")
            self._seit = (_("seit {zeit} Uhr ({art})").format(zeit=seit, art=art) if seit
                          else _("startet …"))
            fd = fortschritt_daten()
            if fd:
                # Wie unter Linux: Prozent und Restzeit, darunter der Balken
                kopf = fortschritt_zeile(fd)
                zeilen = [kopf, balken(fd["prozent"]) + "  " + prozent_text(fd)]
            else:
                zeilen = [kopf, self._seit]
            zeilen += ["", _("Wird nach der Sicherung heruntergefahren.") if self._abschalten
                       else _("Bitte nicht herunterfahren.")]
        else:
            # Erste Zeile in Klartext, gleiche Texte wie unter Linux
            kopf = p.status_zeile()
            letzter = p.letzter_lauf()
            icon = "pbs-desk"
            zeilen = [kopf]
            if not p.eingerichtet() or (letzter and letzter.get("status") == "fehler"):
                icon = "pbs-desk-warnung"
            if letzter and letzter.get("status") == "fehler" and letzter.get("grund"):
                zeilen.append(p.grund_text(letzter["grund"]))
            if d is not None and letzter and letzter.get("status") != "ok":
                zeilen.append(_("Letzter Erfolg: {zeit}").format(zeit=p.zeit_text(d)))
            if alter is not None and alter >= stale:
                icon = "pbs-desk-warnung"
                zeilen.append(_("Backup überfällig ({tage} Tage)").format(tage=alter))
            if self._abschalten:
                zeilen.append(_("Wird nach der Sicherung heruntergefahren."))
        if self._abschalten:
            self.abschalten_pruefen(aktiv)
        self.setIcon(p.symbol(icon))
        # Windows kuerzt den Tooltip auf 127 Zeichen
        self.setToolTip((p.PROGRAMM + "\n" + "\n".join(z for z in zeilen if z))[:127])
        self._aktiv, self._kopf, self._zeilen = aktiv, kopf, zeilen
        self.timer.setInterval(5_000 if aktiv else 10_000)
        # Offenes Menue mitlaufen lassen
        if self._balken is not None:
            try:
                if aktiv:
                    self._kopf_aktion.setText(kopf)
                    self._balken.setText("   " + zeilen[1])
            except RuntimeError:
                self._balken = None

    def geklickt(self, grund):
        if grund == QSystemTrayIcon.ActivationReason.Trigger:
            self.aktualisieren()
            self.showMessage(titel(), "\n".join(z for z in self._zeilen if z), p.symbol("pbs-desk"), 8000)

    # --- Menue -----------------------------------------------------------
    def menue_bauen(self):
        self.aktualisieren()
        m = self.menu
        m.clear()
        m.addAction(p.symbol("pbs-desk"), titel())
        m.addSeparator()
        self._kopf_aktion = m.addAction(self._kopf)
        if not self._aktiv:
            if p.eingerichtet():
                self._kopf_aktion.triggered.connect(self.verlauf_zeigen)
            else:
                self._kopf_aktion.triggered.connect(lambda: self.erhoeht("pbs-settings.pyw"))
        self._balken = None
        if self._aktiv:
            # Textbalken statt QProgressBar: sieht aus wie unter Linux
            self._balken = m.addAction("   " + self._zeilen[1])
            if self._zeilen[1] != self._seit:
                m.addAction("   " + self._seit)
        m.addSeparator()
        if self._aktiv:
            m.addAction(_("Sicherung abbrechen")).triggered.connect(self.abbrechen)
        else:
            m.addAction(_("Backup jetzt starten …")).triggered.connect(self.starten)
            if p.engine_image():
                m.addAction(_("Image jetzt sichern …")).triggered.connect(self.image_starten)
        a = QAction(_("Nach dem Backup herunterfahren"), m)
        a.setCheckable(True)
        a.setChecked(self._abschalten is not None)
        a.toggled.connect(self.abschalten_umschalten)
        m.addAction(a)
        m.addAction(_("Verlauf …")).triggered.connect(self.verlauf_zeigen)
        m.addAction(_("Wiederherstellen …")).triggered.connect(
            lambda: self.erhoeht("pbs-restore.pyw"))
        m.addAction(_("Einstellungen …")).triggered.connect(
            lambda: self.erhoeht("pbs-settings.pyw"))
        m.addSeparator()
        m.addAction(_("Tray beenden")).triggered.connect(QApplication.quit)

    # --- Aktionen --------------------------------------------------------
    def lauf_anstossen(self, aufgabe=p.AUFGABE_HAND):
        r = subprocess.run(["schtasks", "/run", "/tn", aufgabe], capture_output=True,
                           creationflags=subprocess.CREATE_NO_WINDOW)
        if r.returncode != 0:
            QMessageBox.warning(None, p.PROGRAMM, _("Backup konnte nicht gestartet werden.") + "\n\n"
                                + r.stderr.decode("cp850", "replace").strip())
            return False
        QTimer.singleShot(3000, self.aktualisieren)
        return True

    def abbrechen(self):
        if QMessageBox.question(None, p.PROGRAMM, _(
                "Laufende Sicherung abbrechen? Bereits gesicherte Daten bleiben auf dem Server, "
                "die Sicherung ist dann aber unvollständig.")) != QMessageBox.StandardButton.Yes:
            return
        self._abschalten = None
        self.lauf_anstossen(p.AUFGABE_ABBRECHEN)

    def verlauf_zeigen(self):
        VerlaufDialog().exec()

    def starten(self):
        if QMessageBox.question(None, p.PROGRAMM, _("Backup jetzt starten?")) \
                == QMessageBox.StandardButton.Yes:
            self.lauf_anstossen()

    def image_starten(self):
        if QMessageBox.question(None, p.PROGRAMM, _(
                "Image der ganzen Systemplatte jetzt sichern?\n\n"
                "Gedacht vor riskanten Änderungen (Treiber, Updates). Das dauert länger "
                "als ein normales Backup.")) == QMessageBox.StandardButton.Yes:
            self.lauf_anstossen(p.AUFGABE_IMAGE_HAND)

    def abschalten_umschalten(self, an):
        if not an:
            self._abschalten = None
        else:
            self._abschalten = datetime.now().astimezone()
            if not self._aktiv and not self.lauf_anstossen():
                self._abschalten = None
        self.aktualisieren()

    def abschalten_pruefen(self, aktiv):
        """Nach dem Ende des Laufs: nur nach Erfolg herunterfahren."""
        if aktiv:
            return
        neu = [e for e in p.verlauf(20) if e.get("art") == "backup"
               and e.get("zeit", "") >= self._abschalten.isoformat(timespec="seconds")]
        if not neu:
            # Aufgabe hat den Lauf noch nicht begonnen; nach 2 Minuten aufgeben
            if (datetime.now().astimezone() - self._abschalten).total_seconds() > 120:
                self._abschalten = None
            return
        self._abschalten = None
        if neu[-1].get("status") != "ok":
            QMessageBox.warning(None, p.PROGRAMM,
                                _("Backup fehlgeschlagen – der Rechner bleibt an."))
            return
        if AbschaltDialog().exec() == QDialog.DialogCode.Accepted and not herunterfahren():
            QMessageBox.warning(None, p.PROGRAMM, _("Herunterfahren fehlgeschlagen."))

    def erhoeht(self, skript):
        if not p.erhoeht_starten(skript):
            QMessageBox.information(None, p.PROGRAMM, _("Abgebrochen: keine Administratorrechte."))

    # --- Erststart: Symbol sichtbar machen ---------------------------
    def erststart(self):
        """Holt das Symbol einmalig aus dem Ueberlauf in die Taskleiste und sagt, wo es ist.

        Windows 11 merkt sich Infobereich-Symbole unter HKCU\\Control Panel\\NotifyIconSettings;
        IsPromoted=1 zeigt es dauerhaft an. Nur einmal je Benutzer (Vermerk unter
        HKCU\\Software\\PBS-Desk), damit eine spaetere Wahl des Benutzers bleibt."""
        import winreg
        try:
            k = winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\PBS-Desk")
            try:
                if winreg.QueryValueEx(k, "SymbolAngezeigt")[0] == 1:
                    return
            except OSError:
                pass
            gefunden = False
            try:
                basis = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\NotifyIconSettings")
                i = 0
                while True:
                    try:
                        name = winreg.EnumKey(basis, i)
                    except OSError:
                        break
                    i += 1
                    try:
                        sub = winreg.OpenKey(basis, name, 0, winreg.KEY_READ | winreg.KEY_SET_VALUE)
                        pfad = str(winreg.QueryValueEx(sub, "ExecutablePath")[0]).lower()
                    except OSError:
                        continue
                    if pfad.endswith("\\pbs-desk\\python\\pythonw.exe"):
                        winreg.SetValueEx(sub, "IsPromoted", 0, winreg.REG_DWORD, 1)
                        gefunden = True
            except OSError:
                pass
            if not gefunden:
                self._erststart_versuche += 1
                if self._erststart_versuche < 12:   # Explorer legt den Eintrag verzoegert an
                    QTimer.singleShot(5000, self.erststart)
                    return
            winreg.SetValueEx(k, "SymbolAngezeigt", 0, winreg.REG_DWORD, 1)
        except OSError:
            return
        self.showMessage(p.PROGRAMM, _(
            "PBS-Desk sichert diesen Rechner. Das Symbol unten rechts in der Taskleiste zeigt den "
            "Stand, ein Rechtsklick öffnet das Menü."), p.symbol("pbs-desk"), 15000)


class VerlaufDialog(QDialog):
    """Letzte Laeufe in Klartext; das Rohprotokoll nur ueber einen Knopf."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(_("{programm} – Verlauf").format(programm=p.PROGRAMM))
        self.setWindowIcon(p.symbol("pbs-desk"))
        self.resize(760, 420)
        lay = QVBoxLayout(self)
        laeufe = [e for e in reversed(p.verlauf(500)) if e.get("art") in ("backup", "image")][:50]
        t = QTableWidget(len(laeufe), 4)
        t.setHorizontalHeaderLabels([_("Datum"), _("Dauer"), _("Ergebnis"), _("Grund")])
        t.verticalHeader().setVisible(False)
        t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        t.setWordWrap(True)
        for i, e in enumerate(laeufe):
            try:
                datum = datetime.fromisoformat(e["zeit"]).strftime(_("%d.%m.%Y %H:%M"))
            except (KeyError, ValueError):
                datum = "?"
            if e.get("art") == "image":
                datum += " " + _("(Image)")
            if e.get("ausloeser") == "hand":
                datum += " " + _("(von Hand)")
            st = e.get("status")
            ergebnis = {"ok": _("✓ erfolgreich"), "fehler": _("✗ fehlgeschlagen"),
                        "abgebrochen": _("abgebrochen")}.get(st, st or "?")
            grund = "" if st == "ok" else p.grund_text(e.get("grund") or
                                                       ("abgebrochen" if st == "abgebrochen" else "sonstiges"))
            ds = e.get("dauer_s")
            dauer = restzeit(ds) if isinstance(ds, int) and ds > 0 else "–"
            for j, text in enumerate((datum, dauer, ergebnis, grund)):
                it = QTableWidgetItem(text)
                it.setToolTip(text)
                t.setItem(i, j, it)
        kopf = t.horizontalHeader()
        for j in range(3):
            kopf.setSectionResizeMode(j, QHeaderView.ResizeMode.ResizeToContents)
        kopf.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        t.resizeRowsToContents()
        if not laeufe:
            lay.addWidget(QLabel(_("Noch keine Sicherung gelaufen.")))
        lay.addWidget(t, 1)
        zeile = QHBoxLayout()
        b = QPushButton(_("Technisches Protokoll …"))
        b.clicked.connect(self.protokoll)
        zeile.addWidget(b)
        zeile.addStretch(1)
        zu = QPushButton(_("Schließen"))
        zu.clicked.connect(self.accept)
        zeile.addWidget(zu)
        lay.addLayout(zeile)

    def protokoll(self):
        try:
            os.startfile(p.LOG)
        except OSError:
            QMessageBox.information(self, p.PROGRAMM, _("Noch kein Protokoll vorhanden."))


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(p.PROGRAMM)
    app.setApplicationDisplayName(p.PROGRAMM)
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(p.symbol("pbs-desk"))
    p.qt_uebersetzen(app)
    if not QSystemTrayIcon.isSystemTrayAvailable():
        return 1
    tray = Tray()  # noqa: F841
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
