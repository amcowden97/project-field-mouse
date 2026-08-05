# Deployment guide

Raspberry Pi OS 64-bit on Raspberry Pi 5 is the primary platform. The installer creates
an unprivileged `fieldmouse` user, virtual environment, station configuration, migrated
database, systemd services, and maintenance timer.

Set optional `PFM_STATION_NAME`, `PFM_STATION_ID`, and `PFM_TIMEZONE` before
`scripts/install.sh` for unattended installation. Otherwise safe generic values are
used and can be changed through `/etc/fieldmouse/station.toml`.

Units are in `deploy/systemd`. Runtime code lives at `/opt/project-field-mouse`,
configuration at `/etc/fieldmouse/station.toml`, and mutable data under the application
data/log directories. Only the latter paths are writable by services.

Before production use, verify `arecord -l`, run `pfm doctor`, `pfm migrate`,
`pfm health`, and `scripts/verify.sh`, then confirm one recording and detection. Bind
the dashboard only to a trusted LAN or place it behind authenticated TLS.
