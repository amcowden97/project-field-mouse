#!/usr/bin/env bash
set -euo pipefail
cd /opt/project-field-mouse
sudo -u fieldmouse .venv/bin/python -m app.database.maintenance backup
sudo -u fieldmouse git pull --ff-only
sudo -u fieldmouse .venv/bin/pip install -r requirements.txt
sudo cp deploy/systemd/* /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl restart fieldmouse-recorder fieldmouse-birdnet fieldmouse-dashboard
scripts/verify.sh
