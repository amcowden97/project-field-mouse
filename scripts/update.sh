#!/usr/bin/env bash
set -euo pipefail
cd /opt/project-field-mouse
export PFM_CONFIG=/etc/fieldmouse/station.toml
sudo -u fieldmouse .venv/bin/python -m app.cli backup
sudo -u fieldmouse git pull --ff-only
sudo -u fieldmouse .venv/bin/pip install -r requirements.txt
sudo -u fieldmouse .venv/bin/python -m app.cli migrate
sudo cp deploy/systemd/* /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl restart fieldmouse-recorder fieldmouse-birdnet fieldmouse-dashboard
scripts/verify.sh
