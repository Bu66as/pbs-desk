"""PBS-Desk Einstellungen unter Windows (Gegenstueck zu bin/pbs-settings).

Laeuft mit Administratorrechten (der Tray startet es ueber UAC). Schreibt
  C:\\ProgramData\\PBS-Desk\\einstellungen.conf  Uhrzeiten, Sperren, Quelle, VSS
  C:\\ProgramData\\PBS-Desk\\pbs-desk.conf       Backup-Server samt Token
und stellt die Uhrzeiten der Aufgabe \\PBS-Desk\\Sicherung um. Das
Token-Geheimnis wird nie angezeigt; ein leeres Feld laesst es unveraendert.
"""
import os
import re
import subprocess
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import pbsdesk as p  # noqa: E402
from pbsdesk import _  # noqa: E402

from PySide6.QtWidgets import (QApplication, QCheckBox, QDialog, QDialogButtonBox,  # noqa: E402
                               QFormLayout, QGroupBox, QHBoxLayout, QLineEdit, QMessageBox,
                               QPushButton, QSpinBox, QVBoxLayout)

UHRZEIT = re.compile(r"^([01]?\d|2[0-3]):[0-5]\d$")


def uhrzeiten_pruefen(text):
    teile = [t.strip() for t in text.split(",") if t.strip()]
    if not teile or not all(UHRZEIT.match(t) for t in teile):
        return None
    return ",".join(f"{int(t.split(':')[0]):02d}:{t.split(':')[1]}" for t in teile)


def aufgabe_planen(uhrzeiten):
    ausl = ",".join(f"(New-ScheduledTaskTrigger -Daily -At '{u}')" for u in uhrzeiten.split(","))
    ps = (f"$t=@({ausl}); Set-ScheduledTask -TaskPath '\\PBS-Desk\\' -TaskName 'Sicherung' "
          "-Trigger $t | Out-Null")
    r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True,
                       creationflags=subprocess.CREATE_NO_WINDOW)
    return r.returncode == 0


class EinstellungenDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(_("{programm} – Einstellungen").format(programm=p.PROGRAMM))
        self.setWindowIcon(p.symbol("pbs-desk"))
        w, c = p.einstellungen(), p.datei_werte(p.CONF)
        lay = QVBoxLayout(self)

        zeit = QGroupBox(_("Zeitplan"))
        f = QFormLayout(zeit)
        self.uhrzeiten = QLineEdit(w["UHRZEITEN"])
        self.uhrzeiten.setToolTip(_("Mehrere Uhrzeiten mit Komma trennen, z. B. 07:30,12:30,18:00"))
        f.addRow(_("Uhrzeiten:"), self.uhrzeiten)
        self.skip = QCheckBox(_("Während der Arbeitszeit nicht automatisch sichern"))
        self.skip.setChecked(w["ARBEITSZEIT_SKIP"] == "1")
        f.addRow(self.skip)
        zeile = QHBoxLayout()
        self.ws, self.we = QSpinBox(), QSpinBox()
        for s, v in ((self.ws, w["WORK_START"]), (self.we, w["WORK_END"])):
            s.setRange(0, 24)
            s.setValue(int(v))
            s.setSuffix(_(" Uhr"))
            zeile.addWidget(s)
        f.addRow(_("Arbeitszeit (Mo–Fr):"), zeile)
        self.tag = QCheckBox(_("Höchstens ein automatisches Backup pro Tag (Tagessperre)"))
        self.tag.setChecked(w["TAGESSPERRE"] == "1")
        f.addRow(self.tag)
        f.addRow(QLabelHinweis(_("Ein Start von Hand umgeht beide Sperren.")))
        lay.addWidget(zeit)

        quelle = QGroupBox(_("Sicherung"))
        f = QFormLayout(quelle)
        self.quelle = QLineEdit(w["QUELLE"])
        f.addRow(_("Ordner oder Laufwerk:"), self.quelle)
        self.vss = QCheckBox(_("Schattenkopie (VSS) verwenden"))
        self.vss.setChecked(w["VSS"] == "1")
        f.addRow(self.vss)
        lay.addWidget(quelle)

        server = QGroupBox(_("Backup-Server"))
        f = QFormLayout(server)
        u = urllib.parse.urlparse(c.get("PBS_REPOSITORY", ""))
        self.feld = {}
        for k, text, wert in (
                ("host", _("Server:"), u.hostname or ""),
                ("port", _("Port:"), str(u.port or 8007)),
                ("PBS_DATASTORE", _("Datastore:"), c.get("PBS_DATASTORE", "")),
                ("PBS_TOKEN_ID", _("API-Token:"), c.get("PBS_TOKEN_ID", "")),
                ("geheimnis", _("Token-Geheimnis:"), ""),
                ("PBS_NAMESPACE", _("Namespace:"), c.get("PBS_NAMESPACE", "")),
                ("PBS_BACKUP_ID", _("Backup-ID:"), c.get("PBS_BACKUP_ID", "")),
                ("PBS_FINGERPRINT", _("Fingerabdruck:"), c.get("PBS_FINGERPRINT", ""))):
            self.feld[k] = QLineEdit(wert)
            f.addRow(text, self.feld[k])
        self.feld["geheimnis"].setEchoMode(QLineEdit.EchoMode.Password)
        self.feld["geheimnis"].setPlaceholderText(
            _("unverändert") if c.get("PBS_TOKEN_SECRET") else _("fehlt"))
        self.feld["PBS_TOKEN_ID"].setPlaceholderText("benutzer@realm!tokenname")
        self.feld["PBS_BACKUP_ID"].setPlaceholderText(os.environ.get("COMPUTERNAME", "").lower())
        knoepfe = QHBoxLayout()
        b = QPushButton(_("Vom Server holen"))
        b.clicked.connect(self.fingerabdruck_holen)
        knoepfe.addWidget(b)
        b = QPushButton(_("Verbindung testen"))
        b.clicked.connect(self.server_testen)
        knoepfe.addWidget(b)
        f.addRow(knoepfe)
        lay.addWidget(server)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.speichern)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def server_conf(self):
        alt = p.datei_werte(p.CONF)
        host, port = self.feld["host"].text().strip(), self.feld["port"].text().strip() or "8007"
        neu = dict(alt)
        neu["PBS_REPOSITORY"] = f"https://{host}:{port}" if host else ""
        for k in ("PBS_DATASTORE", "PBS_TOKEN_ID", "PBS_NAMESPACE", "PBS_BACKUP_ID", "PBS_FINGERPRINT"):
            neu[k] = self.feld[k].text().strip()
        if self.feld["geheimnis"].text():
            neu["PBS_TOKEN_SECRET"] = self.feld["geheimnis"].text().strip()
        return neu

    def fingerabdruck_holen(self):
        try:
            fp = p.fingerabdruck(self.feld["host"].text().strip(), self.feld["port"].text().strip() or 8007)
        except Exception as e:
            QMessageBox.warning(self, p.PROGRAMM, _("Server nicht erreichbar: {fehler}").format(fehler=e))
            return
        if QMessageBox.question(self, p.PROGRAMM, _("Fingerabdruck des Servers:\n{fp}\n\nÜbernehmen?")
                                .format(fp=fp)) == QMessageBox.StandardButton.Yes:
            self.feld["PBS_FINGERPRINT"].setText(fp)

    def server_testen(self):
        try:
            n = len(p.Server(self.server_conf()).snapshots())
        except Exception as e:
            QMessageBox.warning(self, p.PROGRAMM, _("Verbindung fehlgeschlagen: {fehler}").format(fehler=e))
            return
        QMessageBox.information(self, p.PROGRAMM,
                                _("Verbindung in Ordnung – {n} Sicherungen gefunden.").format(n=n))

    def speichern(self):
        uz = uhrzeiten_pruefen(self.uhrzeiten.text())
        if not uz:
            QMessageBox.warning(self, p.PROGRAMM, _("Uhrzeiten bitte als HH:MM, mit Komma getrennt."))
            return
        if self.ws.value() >= self.we.value():
            QMessageBox.warning(self, p.PROGRAMM, _("Die Arbeitszeit muss vor ihrem Ende beginnen."))
            return
        w = {k: v for k, v in p.datei_werte(p.EINSTELLUNGEN).items()}
        w.update({"UHRZEITEN": uz, "ARBEITSZEIT_SKIP": "1" if self.skip.isChecked() else "0",
                  "WORK_START": str(self.ws.value()), "WORK_END": str(self.we.value()),
                  "TAGESSPERRE": "1" if self.tag.isChecked() else "0",
                  "QUELLE": self.quelle.text().strip() or "C:\\",
                  "VSS": "1" if self.vss.isChecked() else "0"})
        try:
            p.datei_schreiben(p.EINSTELLUNGEN, w, "# PBS-Desk Einstellungen (pbs-settings)")
            p.datei_schreiben(p.CONF, self.server_conf(),
                              "# PBS-Desk Windows - nur SYSTEM und Administratoren lesbar")
        except OSError as e:
            QMessageBox.warning(self, p.PROGRAMM, _("Speichern fehlgeschlagen: {fehler}").format(fehler=e))
            return
        if not aufgabe_planen(uz):
            QMessageBox.warning(self, p.PROGRAMM, _("Die Aufgabenplanung ließ sich nicht umstellen."))
        self.accept()


def QLabelHinweis(text):
    from PySide6.QtWidgets import QLabel
    lab = QLabel(text)
    lab.setStyleSheet("color: gray")
    return lab


def main():
    app = QApplication(sys.argv)
    app.setApplicationDisplayName(p.PROGRAMM)
    p.qt_uebersetzen(app)
    if not p.ist_admin():
        QMessageBox.warning(None, p.PROGRAMM, _("Abgebrochen: keine Administratorrechte."))
        return 1
    return 0 if EinstellungenDialog().exec() else 1


if __name__ == "__main__":
    sys.exit(main())
