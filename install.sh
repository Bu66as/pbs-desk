#!/bin/bash
# install.sh — install, update or remove pbs-desk.
#
#   sudo ./install.sh                 install / update
#   sudo ./install.sh --deps          install the dependencies with the package manager first
#   sudo ./install.sh --with-client   fetch proxmox-backup-client from the official Proxmox
#                                     .deb if it is missing (x86_64 only, for distributions
#                                     without a package, e.g. Fedora)
#   sudo ./install.sh --user NAME     desktop user (default: the user who ran sudo)
#   sudo ./install.sh --uninstall     remove the programs, keep settings
#   sudo ./install.sh --purge         also remove settings, credentials and log
#
# Installs into /usr/local (the programs call each other there).
# An existing /etc/default/pbs-backup is left untouched.
set -euo pipefail

PREFIX=/usr/local
QUELLE=$(cd "$(dirname "$0")" && pwd)
CLIENT_VERSION="4.2.6-1"
CLIENT_SHA256="ef3ad7a2c41d17d936d3cc7af8f99704f19df211a0a98f8993bd4de48b316651"
CLIENT_URL="http://download.proxmox.com/debian/pbs-client/dists/trixie/main/binary-amd64/proxmox-backup-client_${CLIENT_VERSION}_amd64.deb"

SBIN=(pbs-backup pbs-settings pbs-restore-helper)
BIN=(pbs-tray pbs-rate pbs-restore)
ICONS=(pbs-desk pbs-desk-laeuft pbs-desk-warnung)
ICON_DIR=/usr/share/icons/hicolor/scalable/apps
POLKIT=/usr/share/polkit-1/actions/de.exnolim.pbsdesk.policy
MO=$PREFIX/share/locale/en/LC_MESSAGES/pbs-desk.mo
DOC=$PREFIX/share/doc/pbs-desk
CONF=/etc/default/pbs-backup

MIT_DEPS=0; MIT_CLIENT=0; MODUS=install; BENUTZER=${SUDO_USER:-}
while (( $# )); do
  case "$1" in
    --deps)        MIT_DEPS=1 ;;
    --with-client) MIT_CLIENT=1 ;;
    --user)        BENUTZER=${2:?--user needs a name}; shift ;;
    --uninstall)   MODUS=uninstall ;;
    --purge)       MODUS=purge ;;
    -h|--help)     sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown option: $1 (see --help)" >&2; exit 2 ;;
  esac
  shift
done

(( EUID == 0 )) || { echo "Please run with sudo or as root." >&2; exit 1; }
command -v systemctl >/dev/null || { echo "pbs-desk requires systemd." >&2; exit 1; }

info() { printf '  %s\n' "$*"; }

# ------------------------------------------------------------------ Entfernen
entfernen() {
  systemctl disable --now pbs-backup.timer 2>/dev/null || true
  for f in "${SBIN[@]}"; do rm -f "$PREFIX/sbin/$f"; done
  for f in "${BIN[@]}"; do rm -f "$PREFIX/bin/$f"; done
  for f in "${ICONS[@]}"; do rm -f "$ICON_DIR/$f.svg"; done
  rm -f /etc/systemd/system/pbs-backup.service /etc/systemd/system/pbs-backup.timer \
        /etc/xdg/autostart/pbs-tray.desktop /usr/share/applications/pbs-desk-tray.desktop \
        /usr/share/applications/pbs-restore.desktop "$POLKIT" "$MO" /etc/logrotate.d/pbs-backup
  rm -rf "$DOC"
  systemctl daemon-reload
  echo "pbs-desk removed."
  if [[ "$MODUS" == purge ]]; then
    rm -rf /etc/systemd/system/pbs-backup.timer.d /etc/pbs-backup.local "$CONF" \
           /etc/proxmox-backup-client/lokal /var/lib/pbs-backup /var/log/pbs-backup.log*
    systemctl daemon-reload
    echo "Settings, credentials (target lokal) and log removed."
  else
    echo "Kept: $CONF, /etc/pbs-backup.local, /etc/proxmox-backup-client/, /var/log/pbs-backup.log"
  fi
}
if [[ "$MODUS" != install ]]; then entfernen; exit 0; fi

# ------------------------------------------------------------------ Abhaengigkeiten
paketmanager() {
  for pm in dnf zypper apt-get pacman; do command -v $pm >/dev/null && { echo $pm; return; }; done
}
PM=$(paketmanager || true)
case "$PM" in
  dnf)     PAKETE=(python3-pyside6 libnotify polkit curl binutils) ;;
  zypper)  PAKETE=(python3-pyside6 libnotify-tools polkit curl binutils) ;;
  apt-get) PAKETE=(python3-pyside6.qtwidgets libnotify-bin pkexec curl binutils) ;;
  pacman)  PAKETE=(pyside6 libnotify polkit curl binutils) ;;
  *)       PAKETE=() ;;
esac
if (( MIT_DEPS )); then
  [[ -n "$PM" ]] || { echo "No known package manager found, please install the dependencies manually." >&2; exit 1; }
  echo "Installing dependencies with $PM: ${PAKETE[*]}"
  case "$PM" in
    dnf)     dnf install -y "${PAKETE[@]}" ;;
    zypper)  zypper --non-interactive install "${PAKETE[@]}" ;;
    apt-get) apt-get install -y "${PAKETE[@]}" ;;
    pacman)  pacman -S --needed --noconfirm "${PAKETE[@]}" ;;
  esac
fi

FEHLT=()
for c in bash curl python3 notify-send pkexec; do command -v "$c" >/dev/null || FEHLT+=("$c"); done
python3 -c 'import PySide6.QtWidgets' 2>/dev/null || FEHLT+=("PySide6 (Python)")
if (( ${#FEHLT[@]} )); then
  echo "Missing: ${FEHLT[*]}" >&2
  [[ -n "$PM" ]] && echo "With --deps the installer fetches: ${PAKETE[*]}" >&2
  exit 1
fi

# ------------------------------------------------------------------ proxmox-backup-client
if ! command -v proxmox-backup-client >/dev/null; then
  if (( MIT_CLIENT )); then
    [[ "$(uname -m)" == x86_64 ]] || { echo "--with-client is only available for x86_64." >&2; exit 1; }
    command -v ar >/dev/null || { echo "--with-client needs 'ar' (package binutils)." >&2; exit 1; }
    tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
    echo "Downloading proxmox-backup-client $CLIENT_VERSION ..."
    curl -fsSL -o "$tmp/pbc.deb" "$CLIENT_URL"
    echo "$CLIENT_SHA256  $tmp/pbc.deb" | sha256sum -c --quiet
    (cd "$tmp" && ar x pbc.deb data.tar.xz && tar -xJf data.tar.xz ./usr/bin/proxmox-backup-client ./usr/bin/pxar)
    install -m 0755 "$tmp/usr/bin/proxmox-backup-client" "$tmp/usr/bin/pxar" "$PREFIX/bin/"
    "$PREFIX/bin/proxmox-backup-client" version
  else
    cat >&2 <<HINWEIS
proxmox-backup-client is missing.
  Debian/Ubuntu: package proxmox-backup-client from the Proxmox repository
                 (https://pbs.proxmox.com/docs/installation.html#client-installation)
  other (x86_64): sudo ./install.sh --with-client  (downloads the official .deb and
                 extracts the two programs to $PREFIX/bin)
HINWEIS
    exit 1
  fi
fi

# ------------------------------------------------------------------ Dateien
echo "Installing pbs-desk to $PREFIX ..."
for f in "${SBIN[@]}"; do install -Dm 0755 "$QUELLE/bin/$f" "$PREFIX/sbin/$f"; done
for f in "${BIN[@]}";  do install -Dm 0755 "$QUELLE/bin/$f" "$PREFIX/bin/$f"; done
for f in "${ICONS[@]}"; do install -Dm 0644 "$QUELLE/icons/$f.svg" "$ICON_DIR/$f.svg"; done
install -Dm 0644 "$QUELLE/desktop/pbs-tray.desktop"      /etc/xdg/autostart/pbs-tray.desktop
install -Dm 0644 "$QUELLE/desktop/pbs-desk-tray.desktop" /usr/share/applications/pbs-desk-tray.desktop
install -Dm 0644 "$QUELLE/desktop/pbs-restore.desktop"   /usr/share/applications/pbs-restore.desktop
install -Dm 0644 "$QUELLE/polkit/de.exnolim.pbsdesk.policy" "$POLKIT"
install -Dm 0644 "$QUELLE/systemd/pbs-backup.service" /etc/systemd/system/pbs-backup.service
install -Dm 0644 "$QUELLE/systemd/pbs-backup.timer"   /etc/systemd/system/pbs-backup.timer
install -Dm 0644 "$QUELLE/config/logrotate.pbs-backup" /etc/logrotate.d/pbs-backup
install -Dm 0644 "$QUELLE/config/pbs-backup.conf.example" "$DOC/pbs-backup.conf.example"
install -Dm 0644 "$QUELLE/README.md" "$DOC/README.md"
install -Dm 0644 "$QUELLE/README.en.md" "$DOC/README.en.md"
install -d -m 0755 "$(dirname "$MO")"
python3 "$QUELLE/tools/msgfmt.py" "$MO" "$QUELLE"/po/en/*.po
chmod 0644 "$MO"
touch "$ICON_DIR" 2>/dev/null || true
command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -q /usr/share/icons/hicolor 2>/dev/null || true

install -d -m 0755 /var/lib/pbs-backup /etc/proxmox-backup-client /etc/default /var/log
[[ -e /var/log/pbs-backup.log ]] || install -m 0644 /dev/null /var/log/pbs-backup.log

# Handschalter-Datei gehoert dem Desktop-Benutzer (pbs-rate laeuft ohne root)
if [[ -n "$BENUTZER" ]] && id "$BENUTZER" >/dev/null 2>&1; then
  [[ -e /var/lib/pbs-backup/rate.override ]] || install -m 0644 /dev/null /var/lib/pbs-backup/rate.override
  chown "$BENUTZER": /var/lib/pbs-backup/rate.override
else
  echo "Note: no desktop user known (--user NAME); notifications and the manual bandwidth switch stay off." >&2
  BENUTZER=""
fi

# Grundkonfiguration nur, wenn es noch keine gibt. VERWALTET=0 gibt im
# Einstellungsfenster den Abschnitt "Backup-Server" frei.
if [[ ! -e "$CONF" ]]; then
  NAME=$(hostname -s)
  cat > "$CONF" <<KONF
# pbs-desk — Grundeinstellungen (angelegt von install.sh).
# Vollstaendige Beispielkonfiguration: $DOC/pbs-backup.conf.example
# Der Backup-Server wird im Tray unter "Einstellungen" eingetragen.

DEVICE_NAME="$NAME"
BACKUP_ID="$NAME"
PBS_NS=""
MOBIL=0
# 0 = Server im Einstellungsfenster frei waehlbar
VERWALTET=0
NOTIFY_USER="$BENUTZER"

EXCLUDES=(
  "/*/.cache"
  "/*/.local/share/Trash"
  "/*/.local/share/containers"
  "/var/cache"
  "/var/tmp"
  "/var/lib/flatpak"
  "/var/lib/plocate"
  "/var/lib/containers"
)
KONF
  chmod 0644 "$CONF"
  info "$CONF created"
else
  info "$CONF exists, left unchanged"
fi

systemctl daemon-reload
systemctl enable --now pbs-backup.timer >/dev/null
command -v snapper >/dev/null || info "snapper not found: the running system is backed up instead of a btrfs snapshot"

cat <<FERTIG

pbs-desk is installed.
  1. Log out and back in (or run "pbs-tray &"); the icon appears in the system tray.
  2. Right-click > Settings > Backup server: enter server, datastore and API token.
  3. Right-click > Start backup now, or wait for the timer (17:00, 19:00, 21:00, 23:00).
     Backups run on AC power only and, by default, not Mon-Fri 8:00-17:00.
FERTIG
