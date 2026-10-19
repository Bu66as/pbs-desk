# pbs-desk

[Deutsch](README.md)

Desktop client for Proxmox Backup Server: backs up Linux notebooks and PCs
automatically with `proxmox-backup-client`, shows the state in the system tray
and restores files with a few clicks.

A project by ExNoLim. pbs-desk is not a product of Proxmox Server Solutions
GmbH, is not supported by it and is not affiliated with it. Proxmox® is a
registered trademark of Proxmox Server Solutions GmbH in the EU, the U.S. and
other countries.

## Status

Early release. pbs-desk has been in daily use for weeks on several Linux
notebooks (Fedora, KDE Plasma). Other distributions and desktops have seen
little testing. There are no RPM/DEB packages yet; install with `install.sh`.

## Installation

Requirements: systemd, Python 3 with PySide6, `notify-send`, `pkexec`, `curl`
and `proxmox-backup-client`. Optional: `snapper` for btrfs snapshots.

```bash
git clone https://github.com/Bu66as/pbs-desk.git
cd pbs-desk
sudo ./install.sh --deps            # dependencies via dnf/apt/zypper/pacman
# no package for proxmox-backup-client (e.g. Fedora, x86_64 only):
sudo ./install.sh --deps --with-client
```

Log out and back in. In the tray: right-click > Settings > Backup server.
Enter server, port, datastore, API token and namespace. The server fingerprint
is fetched and shown for confirmation. The token is stored readable by root
only under `/etc/proxmox-backup-client/lokal/`.

On the Proxmox Backup Server the token needs the `DatastoreBackup` role on the
datastore or namespace. That is also enough to restore its own backups.

Remove: `sudo ./install.sh --uninstall` (keeps settings) or `--purge`
(removes everything).

Language: the interface and notifications are available in German and English,
chosen from `LANGUAGE`/`LANG` (German for `de*`, English otherwise). The log
`/var/log/pbs-backup.log` is written in German.

## Features

- Backs up `/` and `/home` as `root.pxar` and `home.pxar`
- Snapper snapshot (btrfs) before the run; the frozen state is backed up
- Your own server from the settings dialog, or two centrally configured targets:
  unthrottled on the LAN, throttled to an offsite target when travelling
- Rules: no backups during working hours, at most one successful run per day,
  only on AC power
- Tray icon with status, manual bandwidth switch and settings dialog
- "Shut down after the backup" from the tray (60 s countdown, only after a
  successful run; on failure or skip the computer stays on)
- Desktop notifications on start, success and failure
- Restore: list backups, mount an archive read-only and open it in the file
  manager; plus a history of backup runs

## Layout

| Path                              | Content                                        |
|-----------------------------------|------------------------------------------------|
| `bin/pbs-backup`                  | Backup run (Bash), started by the timer        |
| `bin/pbs-tray`                    | Tray and settings dialog (Python, PySide6)     |
| `bin/pbs-settings`                | Root helper for local settings                 |
| `bin/pbs-rate`                    | Manual bandwidth switch                        |
| `bin/pbs-restore`                 | Restore and history (Python, PySide6)          |
| `bin/pbs-restore-helper`          | Root helper: list and mount backups            |
| `polkit/`                         | Polkit policy for the root helpers             |
| `systemd/`                        | Service and timer                              |
| `config/pbs-backup.conf.example`  | Example configuration                          |
| `po/en/`                          | English translation (gettext)                  |
| `install.sh`                      | Install, update, remove                        |

## Restore: how privileges are split

The backup server credentials are readable by root only, under
`/etc/proxmox-backup-client/`. The interface never sees them; it calls the
root helper through `pkexec` (administrator authentication, cached for a few
minutes). The helper mounts the backup with the ID of the logged-in user, so
the mounted tree has the same file permissions as the running system: other
users' home directories and system files the user cannot read stay closed in
the backup too. The token reaches `proxmox-backup-client` through an inherited
file descriptor and appears neither on the command line nor in the
environment. The mount process does run as the user and keeps the token in
memory.

## Planned

1. RPM and DEB packages
2. One program instead of separate scripts, with CLI, GUI and root helper
3. Restore for encrypted backups (key file)
4. Snapper, second target, rules and throttling as optional features

## License

GPL-3.0-or-later, see `LICENSE`.
