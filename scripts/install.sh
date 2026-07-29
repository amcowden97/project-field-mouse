#!/usr/bin/env bash
set -euo pipefail
[[ "$(uname -s)" == "Linux" ]] || { echo "Installer requires Linux"; exit 1; }
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else "Python 3.11+ is required")'
if [[ -r /proc/device-tree/model ]]; then
    MODEL="$(tr -d '\0' </proc/device-tree/model)"
    echo "Detected hardware: $MODEL"
else
    echo "Warning: Raspberry Pi model information was not detected."
fi
sudo apt-get update
sudo apt-get install -y python3-venv alsa-utils libsndfile1
sudo id fieldmouse >/dev/null 2>&1 || sudo useradd --system --home /opt/project-field-mouse --shell /usr/sbin/nologin fieldmouse
sudo usermod -a -G audio fieldmouse
sudo mkdir -p /opt/project-field-mouse /etc/fieldmouse
sudo cp -a "$ROOT/." /opt/project-field-mouse/
sudo python3 -m venv /opt/project-field-mouse/.venv
sudo /opt/project-field-mouse/.venv/bin/pip install --upgrade pip
sudo /opt/project-field-mouse/.venv/bin/pip install -r /opt/project-field-mouse/requirements.txt gunicorn
sudo chown -R fieldmouse:fieldmouse /opt/project-field-mouse
if [[ ! -f /etc/fieldmouse/station.toml ]]; then
    sudo /opt/project-field-mouse/.venv/bin/python -m app.cli \
        --config /etc/fieldmouse/station.toml config init \
        --name "${PFM_STATION_NAME:-Project Field Mouse}" \
        --station-id "${PFM_STATION_ID:-field-mouse-$(hostname)}" \
        --timezone "${PFM_TIMEZONE:-UTC}"
fi
sudo chown root:fieldmouse /etc/fieldmouse/station.toml
sudo chmod 0640 /etc/fieldmouse/station.toml
sudo cp "$ROOT"/deploy/systemd/* /etc/systemd/system/
sudo systemctl daemon-reload
sudo -u fieldmouse /opt/project-field-mouse/.venv/bin/python -m app.cli \
    --config /etc/fieldmouse/station.toml migrate
sudo -u fieldmouse /opt/project-field-mouse/.venv/bin/python -m app.cli \
    --config /etc/fieldmouse/station.toml doctor || true
sudo systemctl enable --now fieldmouse-recorder fieldmouse-birdnet fieldmouse-dashboard fieldmouse-maintenance.timer
if /opt/project-field-mouse/scripts/verify.sh; then
    echo "Project Field Mouse installation verified successfully."
else
    echo "Installation completed, but verification failed. Run: scripts/pfm doctor" >&2
    exit 1
fi
