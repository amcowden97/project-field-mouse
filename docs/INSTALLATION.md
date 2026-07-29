# Installation and station setup

On 64-bit Raspberry Pi OS:

```bash
git clone https://github.com/amcowden97/project-field-mouse.git
cd project-field-mouse
./scripts/install.sh
sudoedit /etc/fieldmouse/station.toml
sudo systemctl restart fieldmouse-recorder fieldmouse-birdnet fieldmouse-dashboard
./scripts/verify.sh
```

Set a unique permanent station ID, name, IANA timezone, ALSA device (`arecord -l`),
and approximate coordinates. Open `http://<pi-hostname>:8000`.

Configuration precedence is environment, TOML, then defaults. `PFM_CONFIG` selects a
file; other overrides use `PFM_SECTION_KEY`, such as `PFM_DASHBOARD_PORT=8080`.
Comma-separate list values.

Use `scripts/update.sh` for backup/update/restart/verification and `scripts/repair.sh`
to restore dependencies, permissions, units, and failed services without replacing
station configuration.

Back up with `python -m app.database.maintenance backup`. Check with the `check`
action. For restore, stop services, run `restore --file BACKUP`, then restart them.
Copy backups and `/etc/fieldmouse` off the Pi periodically.
