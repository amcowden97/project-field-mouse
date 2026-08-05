#!/usr/bin/env bash
set -euo pipefail
cd /opt/project-field-mouse
sudo .venv/bin/pip install -r requirements.txt
sudo cp deploy/systemd/* /etc/systemd/system/
sudo mkdir -p data logs
sudo chown -R fieldmouse:fieldmouse data logs
sudo systemctl daemon-reload
sudo systemctl reset-failed
sudo systemctl restart fieldmouse-recorder fieldmouse-birdnet fieldmouse-dashboard
scripts/verify.sh
