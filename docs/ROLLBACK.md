# Production rollback

Each successful deployment keeps immutable releases and records the prior target in
`/opt/project-field-mouse/previous`. A verified pre-deployment database archive is
stored under `/var/lib/fieldmouse/backups`.

The first `/opt` deployment also preserves the original `/home/amcowden97` checkout,
its unit files, and an online database copy. When no prior immutable release exists,
`pfm-rollback` restores those legacy units and leaves their original database untouched.

Failed deployment validation automatically switches `current` back, restores the
pre-deploy database when one was created, reloads systemd, and restarts the previous
services. The failed release remains available for diagnosis.

For an operator-initiated code rollback:

```bash
sudo -n /usr/local/sbin/pfm-rollback
```

When the release included a database migration, provide its matching verified backup:

```bash
sudo -n /usr/local/sbin/pfm-rollback \
  --backup /var/lib/fieldmouse/backups/predeploy-RELEASE_ID.zip
```

The rollback stops services before changing the release or database, validates the
archive before restore, restarts all services, and requires the health endpoint to
pass. It swaps `previous` to the release that was just replaced, allowing a deliberate
roll-forward if needed.

Never manually edit the `current` symlink or copy database files while services run.
