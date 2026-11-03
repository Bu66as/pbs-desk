"""PBS-Desk Wiederherstellen unter Windows (Gegenstueck zu bin/pbs-restore).

Laeuft mit Administratorrechten (der Tray startet es ueber UAC), denn nur so
ist das Token in pbs-desk.conf lesbar. Durchsucht den Katalog einer Sicherung
ueber die PBS-API und holt Dateien oder ganze Ordner (zip) in einen Zielordner.

Ohne Fenster, z. B. fuer Tests:
  python.exe pbs-restore.pyw --liste
  python.exe pbs-restore.pyw --pfad "/<archiv>.pxar.didx/Users/Public/x.txt" --ziel D:\\ziel [--snapshot N]
"""
import base64
import os
import sys
import tempfile
import zipfile
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import pbsdesk as p  # noqa: E402
from pbsdesk import _  # noqa: E402

STANDARD_ZIEL = os.path.join(p.DATEN, "restore-test")


def snap_text(s):
    return datetime.fromtimestamp(s["backup-time"]).strftime(_("%d.%m.%Y %H:%M")) + f"  ({s['backup-id']})"


def eintrag_pfad(e):
    return base64.b64decode(e["filepath"]).decode("utf-8", "replace")


def holen(server, snap, pfad, ziel, ist_ordner):
    """Holt pfad aus snap nach ziel; Ordner kommen als zip und werden entpackt."""
    os.makedirs(ziel, exist_ok=True)
    name = pfad.rstrip("/").rsplit("/", 1)[-1] or "wiederhergestellt"
    if ist_ordner:
        fd, tmp = tempfile.mkstemp(suffix=".zip", dir=ziel)
        os.close(fd)
        try:
            server.herunterladen(snap, pfad, tmp)
            with zipfile.ZipFile(tmp) as z:
                z.extractall(ziel)
        finally:
            os.remove(tmp)
        return os.path.join(ziel, name)
    aus = os.path.join(ziel, name)
    server.herunterladen(snap, pfad, aus)
    return aus


def protokollieren(status, pfad, ziel, snap=None, fehler=None):
    mehr = {"pfad": pfad, "ziel": ziel}
    if snap:
        mehr["snapshot"] = snap["backup-time"]
    if fehler:
        mehr["meldung"] = str(fehler)[:300]
    try:
        p.verlauf_schreiben("restore", "hand", status, **mehr)
    except OSError:
        pass


def cli(args):
    server = p.Server()
    snaps = server.snapshots()
    if "--liste" in args:
        for i, s in enumerate(snaps):
            print(i, snap_text(s), " ".join(f["filename"] for f in s.get("files", [])))
        return 0
    pfad = args[args.index("--pfad") + 1]
    ziel = args[args.index("--ziel") + 1] if "--ziel" in args else STANDARD_ZIEL
    snap = snaps[int(args[args.index("--snapshot") + 1])] if "--snapshot" in args else snaps[0]
    try:
        aus = holen(server, snap, pfad, ziel, pfad.endswith("/"))
    except Exception as e:
        protokollieren("fehler", pfad, ziel, snap, e)
        print("FEHLER:", e)
        return 1
    protokollieren("ok", pfad, ziel, snap)
    print("OK:", aus)
    return 0


def gui():
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QFileDialog, QHBoxLayout,
                                   QLabel, QLineEdit, QMessageBox, QPushButton, QTreeWidget,
                                   QTreeWidgetItem, QVBoxLayout)
    app = QApplication(sys.argv)
    app.setApplicationDisplayName(p.PROGRAMM)
    p.qt_uebersetzen(app)
    if not p.ist_admin():
        QMessageBox.warning(None, p.PROGRAMM, _("Abgebrochen: keine Administratorrechte."))
        return 1
    try:
        server = p.Server()
        snaps = server.snapshots()
    except Exception as e:
        QMessageBox.warning(None, p.PROGRAMM, _("Verbindung fehlgeschlagen: {fehler}").format(fehler=e))
        return 1
    if not snaps:
        QMessageBox.information(None, p.PROGRAMM, _("Noch keine Sicherung auf dem Server."))
        return 1

    PFAD, ORDNER = Qt.ItemDataRole.UserRole, Qt.ItemDataRole.UserRole + 1
    dlg = QDialog()
    dlg.setWindowTitle(_("{programm} – Wiederherstellen").format(programm=p.PROGRAMM))
    dlg.setWindowIcon(p.symbol("pbs-desk"))
    dlg.resize(720, 520)
    lay = QVBoxLayout(dlg)
    zeile = QHBoxLayout()
    zeile.addWidget(QLabel(_("Sicherung:")))
    auswahl = QComboBox()
    for s in snaps:
        auswahl.addItem(snap_text(s))
    zeile.addWidget(auswahl, 1)
    lay.addLayout(zeile)
    baum = QTreeWidget()
    baum.setHeaderLabels([_("Name")])
    lay.addWidget(baum, 1)
    zeile = QHBoxLayout()
    zeile.addWidget(QLabel(_("Ziel:")))
    ziel = QLineEdit(STANDARD_ZIEL)
    zeile.addWidget(ziel, 1)
    wahl = QPushButton(_("Ordner wählen …"))
    wahl.clicked.connect(lambda: ziel.setText(
        QFileDialog.getExistingDirectory(dlg, _("Zielordner"), ziel.text()) or ziel.text()))
    zeile.addWidget(wahl)
    lay.addLayout(zeile)
    hinweis = QLabel(_("Gleichnamige Dateien im Zielordner werden überschrieben."))
    hinweis.setWordWrap(True)
    hinweis.setStyleSheet("color: gray")
    lay.addWidget(hinweis)
    knoepfe = QHBoxLayout()
    los = QPushButton(_("Wiederherstellen"))
    zu = QPushButton(_("Schließen"))
    knoepfe.addStretch(1)
    knoepfe.addWidget(los)
    knoepfe.addWidget(zu)
    lay.addLayout(knoepfe)
    zu.clicked.connect(dlg.reject)

    def fuellen(eltern, pfad):
        snap = snaps[auswahl.currentIndex()]
        try:
            eintraege = server.katalog(snap, pfad)
        except Exception as e:
            QMessageBox.warning(dlg, p.PROGRAMM, _("Katalog nicht lesbar: {fehler}").format(fehler=e))
            return
        for e in sorted(eintraege, key=lambda x: (x.get("leaf", True), x.get("text", "").lower())):
            it = QTreeWidgetItem([e.get("text", "?")])
            it.setData(0, PFAD, eintrag_pfad(e))
            ordner = not e.get("leaf", True)
            it.setData(0, ORDNER, ordner)
            if ordner:
                it.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)
            (eltern.addChild if eltern else baum.addTopLevelItem)(it)

    def aufklappen(it):
        if it.childCount() == 0:
            fuellen(it, it.data(0, PFAD))

    def neu():
        baum.clear()
        fuellen(None, "/")

    def wiederherstellen():
        it = baum.currentItem()
        if not it:
            return
        pfad, ordner = it.data(0, PFAD), bool(it.data(0, ORDNER))
        snap = snaps[auswahl.currentIndex()]
        app.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            aus = holen(server, snap, pfad, ziel.text(), ordner)
        except Exception as e:
            app.restoreOverrideCursor()
            protokollieren("fehler", pfad, ziel.text(), snap, e)
            QMessageBox.warning(dlg, p.PROGRAMM, _("Wiederherstellen fehlgeschlagen: {fehler}").format(fehler=e))
            return
        app.restoreOverrideCursor()
        protokollieren("ok", pfad, ziel.text(), snap)
        QMessageBox.information(dlg, p.PROGRAMM, _("Wiederhergestellt nach:\n{ziel}").format(ziel=aus))

    baum.itemExpanded.connect(aufklappen)
    auswahl.currentIndexChanged.connect(neu)
    los.clicked.connect(wiederherstellen)
    neu()
    return 0 if dlg.exec() else 0


if __name__ == "__main__":
    a = sys.argv[1:]
    sys.exit(cli(a) if ("--liste" in a or "--pfad" in a) else gui())
