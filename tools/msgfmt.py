#!/usr/bin/env python3
"""Minimaler .po -> .mo-Compiler (kein gettext-Paket noetig).

Aufruf: msgfmt.py ZIEL.mo QUELLE.po [QUELLE.po ...]
Mehrere .po-Dateien werden zu einem Katalog zusammengefasst. Unterstuetzt
msgctxt nicht, nur msgid/msgstr mit mehrzeiligen Strings; leere msgstr
werden ausgelassen (dann gilt der deutsche Ausgangstext).
"""
import ast
import struct
import sys


def lesen(pfad):
    eintraege, msgid, msgstr, feld = {}, None, None, None

    def ablegen():
        if msgid is not None and msgstr:
            eintraege[msgid] = msgstr

    with open(pfad, encoding="utf-8") as f:
        for nr, zeile in enumerate(f, 1):
            zeile = zeile.strip()
            if not zeile or zeile.startswith("#"):
                continue
            if zeile.startswith("msgid "):
                ablegen()
                msgid, msgstr, feld = ast.literal_eval(zeile[6:]), None, "id"
            elif zeile.startswith("msgstr "):
                msgstr, feld = ast.literal_eval(zeile[7:]), "str"
            elif zeile.startswith('"'):
                teil = ast.literal_eval(zeile)
                if feld == "id":
                    msgid += teil
                elif feld == "str":
                    msgstr += teil
            else:
                sys.exit(f"{pfad}:{nr}: unbekannte Zeile: {zeile}")
    ablegen()
    return eintraege


def schreiben(ziel, eintraege):
    schluessel = sorted(eintraege)
    ids = b"".join(k.encode() + b"\0" for k in schluessel)
    strs = b"".join(eintraege[k].encode() + b"\0" for k in schluessel)
    n = len(schluessel)
    kopf = 7 * 4
    o_ids, o_strs = kopf, kopf + n * 8
    daten = o_strs + n * 8
    tab_ids, tab_strs, pos = [], [], daten
    for k in schluessel:
        laenge = len(k.encode())
        tab_ids += [laenge, pos]
        pos += laenge + 1
    for k in schluessel:
        laenge = len(eintraege[k].encode())
        tab_strs += [laenge, pos]
        pos += laenge + 1
    with open(ziel, "wb") as f:
        f.write(struct.pack("<7I", 0x950412DE, 0, n, o_ids, o_strs, 0, 0))
        f.write(struct.pack(f"<{2 * n}I", *tab_ids))
        f.write(struct.pack(f"<{2 * n}I", *tab_strs))
        f.write(ids + strs)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    alle = {}
    for p in sys.argv[2:]:
        alle.update(lesen(p))
    schreiben(sys.argv[1], alle)
