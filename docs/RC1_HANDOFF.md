# Infrastructure handoff for Integration & Release

Run these commands from a fresh operator login on the Raspberry Pi:

```bash
sudo -n true
deploy/production/validate-production.sh

sudo -n /usr/bin/systemctl status fieldmouse-recorder.service
sudo -n /usr/bin/systemctl status fieldmouse-birdnet.service
sudo -n /usr/bin/systemctl status fieldmouse-dashboard.service
sudo -n /usr/bin/systemctl status fieldmouse-backup.timer
sudo -n /usr/bin/systemctl status fieldmouse-cleanup.timer

sudo -n /usr/bin/journalctl --no-pager -n 200 -u fieldmouse-recorder.service
sudo -n /usr/bin/journalctl --no-pager -n 200 -u fieldmouse-birdnet.service
sudo -n /usr/bin/journalctl --no-pager -n 200 -u fieldmouse-dashboard.service

curl --fail http://127.0.0.1:8000/health
curl --fail http://127.0.0.1:8000/api/metrics
```

Confirm that `/usr/bin/id`, `/bin/sh`, arbitrary service names, and package-manager
commands are denied by `sudo -n`. Then perform one dashboard restart and one on-demand
backup using `validate-production.sh`.

For a candidate build:

```bash
sudo -n /usr/local/sbin/pfm-deploy \
  --source "$PWD" --release-id "rc1-$(git rev-parse --short=12 HEAD)"
deploy/production/validate-production.sh
```

For rollback, use the exact commands in `docs/ROLLBACK.md`. No release merge or tag is
part of this handoff.
