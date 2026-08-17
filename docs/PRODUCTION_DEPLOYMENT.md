# RC1 production deployment

## Directory layout

```text
/opt/project-field-mouse/
  current -> releases/<release-id>       active immutable release
  previous -> releases/<release-id>      rollback target
  releases/<release-id>/
    .venv/                               release-specific Python environment
    app/, deploy/, ...                   root-owned application

/etc/fieldmouse/station.toml             root:fieldmouse 0640
/etc/default/fieldmouse                  optional environment overrides
/var/lib/fieldmouse/
  database/fieldmouse.db
  recordings/
  backups/
/var/log/fieldmouse/                     application logs
/var/log/project-field-mouse-reliability/ root:pfm-operators telemetry
```

Application releases and virtual environments become root-owned after dependency
installation. Services run as `fieldmouse` and can write only shared state and logs.

## Service and startup sequence

```text
local filesystems + sound
            |
            v
 fieldmouse-recorder
            |
            v
  fieldmouse-birdnet

network.target --> fieldmouse-dashboard (Gunicorn)

fieldmouse-backup.timer  --> verified compressed backup
fieldmouse-cleanup.timer --> retention cleanup
fieldmouse-reliability.timer --> five-minute metrics + abnormal snapshots
```

Systemd restarts long-running services after failures. Backup, cleanup, and reliability
collection are separate oneshot services and persistent timers, so a missed run occurs
after the next boot. Reliability collection observes services but never restarts them.

## One-command deployment

After the one-time sudo bootstrap and a new operator login:

```bash
sudo -n /usr/local/sbin/pfm-deploy \
  --source /path/to/validated/project-field-mouse \
  --release-id rc1-COMMIT
```

The command serializes deployments with `flock`, creates a verified database and
configuration backup, copies a clean source tree, creates a release-specific virtual
environment, installs production dependencies including Gunicorn, runs migrations,
installs units, disables known legacy timers, atomically switches `current`, enables
and restarts services, and checks every service, timer, and `/health`.

Any error after the switch triggers automatic rollback. Deployments do not merge
branches, create tags, or pull source.

## Startup and shutdown

Recorder starts after sound and local filesystems. BirdNET starts after recorder.
Dashboard starts after network and shared storage. All use the same configuration and
working directory. During rollback, long-running services stop before the release or
database changes and restart only after the prior state is restored.
