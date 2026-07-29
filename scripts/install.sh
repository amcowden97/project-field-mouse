#!/usr/bin/env bash
set -euo pipefail
[[ "$(uname -s)" == "Linux" ]] || { echo "Installer requires Linux"; exit 1; }
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
sudo apt-get update
sudo apt-get install -y python3-venv alsa-utils libsndfile1
sudo id fieldmouse >/dev/null 2>&1 || sudo useradd --system --home /opt/project-field-mouse --shell /usr/sbin/nologin fieldmouse
sudo usermod -a -G audio fieldmouse
sudo mkdir -p /opt/project-field-mouse /etc/fieldmouse
sudo cp -a "$ROOT/." /opt/project-field-mouse/
sudo python3 -m venv /opt/project-field-mouse/.venv
sudo /opt/project-field-mouse/.venv/bin/pip install --upgrade pip
sudo /opt/project-field-mouse/.venv/bin/pip install -r /opt/project-field-mouse/requirements.txt gunicorn
[[ -f /etc/fieldmouse/station.toml ]] || sudo cp "$ROOT/config/station.toml" /etc/fieldmouse/station.toml
sudo chown -R fieldmouse:fieldmouse /opt/project-field-mouse
sudo cp "$ROOT"/deploy/systemd/* /etc/systemd/system/
sudo systemctl daemon-reload
sudo -u fieldmouse /opt/project-field-mouse/.venv/bin/python -m app.database.maintenance init --config /etc/fieldmouse/station.toml
sudo systemctl enable --now fieldmouse-recorder fieldmouse-birdnet fieldmouse-dashboard fieldmouse-maintenance.timer
echo "Installed. Edit /etc/fieldmouse/station.toml, then run scripts/verify.sh."
