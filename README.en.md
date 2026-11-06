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
little testing. There are no RPM/DEB packages yet; install with `install.sh` on Linux or the Setup.exe on Windows.

## Installation

Requirements: systemd, Python 3 with PySide6, `notify-send`, `pkexec`, `curl`
and `proxmox-backup-client`. Optional: `snapper` for btrfs snapshots.

Update the system first (`sudo dnf upgrade` or `apt upgrade`). On a freshly
installed Fedora that was never updated, `--deps` can otherwise fail on file
conflicts between distribution packages.

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

## Installing on Windows

You need Windows 10 or 11 (64-bit) and an account with administrator rights.
The installer includes Python and everything else it needs, so no internet
connection is required during setup.

1. Download the installer, `PBS-Desk-Setup-<version>.exe` (the "Setup.exe"). Until there is a release, the
   "Windows setup" workflow (Actions) provides the file as an artifact. You can
   also build it yourself with `windows\installer\build.ps1` (needs Inno Setup 6).
2. Double-click the file. The programs are not code-signed, so Windows
   SmartScreen shows "Windows protected your PC". Click "More info", then
   "Run anyway".
3. The wizard asks for a language and shows the license. On the "Backup server"
   page, enter server, port, datastore, namespace, backup ID and API token.
   "Fetch from server" retrieves the fingerprint. The token needs the
   `DatastoreBackup` role on the datastore or namespace.
4. Afterwards PBS-Desk is listed under Settings > Apps > Installed apps
   (formerly "Apps & Features"). The tray icon first appears in the overflow
   area (`^`) of the taskbar. File backups run as the scheduled task
   `\PBS-Desk\Sicherung` (morning, noon and evening), and the disk image every
   four weeks.

Programs go to `C:\Program Files\PBS-Desk`; settings, history and credentials
go to `C:\ProgramData\PBS-Desk`.

Silent installation (for example from a software distribution tool):

```powershell
PBS-Desk-Setup-<version>.exe /VERYSILENT /SUPPRESSMSGBOXES /CONFIG=C:\path\pbs-desk.conf
```

`/CONFIG` is optional. It copies a prepared `pbs-desk.conf`, but only if no
configuration exists yet. An existing configuration is never changed by the
installer. The token never appears on a command line or in the setup log.

Uninstalling: Installed apps > PBS-Desk > Uninstall, or silently with
`"C:\Program Files\PBS-Desk\unins000.exe" /VERYSILENT`. This removes the
scheduled tasks, the autostart entry and the program folder. It deletes
`C:\ProgramData\PBS-Desk` only if you say yes (the default is to keep it), and
a silent uninstall always keeps it.

Engine and license: backups are made by `pbsdirectorybackup.exe` (files, using
VSS) and `pbsmachinebackup.exe` (disk image) from
[tizbac/proxmoxbackupclient_go](https://github.com/tizbac/proxmoxbackupclient_go),
version v1.1.3, GPL-3.0. Both are included unmodified; only
`pbsdirectorybackup.exe` is renamed to `proxmoxbackup-directory.exe`. The build
downloads the release and checks it against `checksums.txt`. The source for this
version is the tag
[v1.1.3](https://github.com/tizbac/proxmoxbackupclient_go/tree/v1.1.3), and the
license text is installed next to the programs. See
`windows/installer/THIRD-PARTY.md` for details.

Limits of the file backup: it does not keep NTFS ACLs, alternate data streams
(ADS), file attributes or hardlinks, only content, names and folder structure.
Use the disk image if you need those, or a bootable system after a disk failure
(`windows/IMAGE.md`, in German, covers restoring an image onto a new SSD).
Without the installer you can also run
`powershell -ExecutionPolicy Bypass -File windows\install.ps1` as administrator
from the unpacked repo.

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
