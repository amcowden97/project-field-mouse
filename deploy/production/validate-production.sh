#!/usr/bin/env bash
set -Eeuo pipefail

readonly SERVICES=(
    fieldmouse-recorder.service
    fieldmouse-birdnet.service
    fieldmouse-dashboard.service
)
readonly TIMERS=(
    fieldmouse-backup.timer
    fieldmouse-cleanup.timer
    fieldmouse-reliability.timer
)

[[ $EUID -ne 0 ]] || {
    echo "Run validation as the Integration & Release operator, not root." >&2
    exit 1
}

echo "1/8 Validating narrowly scoped passwordless sudo..."
sudo -n true
if sudo -n /usr/bin/id >/dev/null 2>&1; then
    echo "FAIL: unrelated command '/usr/bin/id' was allowed." >&2
    exit 1
fi
if sudo -n /bin/sh -c true >/dev/null 2>&1; then
    echo "FAIL: an unrestricted root shell was allowed." >&2
    exit 1
fi

echo "2/8 Validating release layout and ownership..."
CURRENT="$(readlink -f /opt/project-field-mouse/current)"
[[ "$CURRENT" == /opt/project-field-mouse/releases/* && -d "$CURRENT" ]]
[[ -x "$CURRENT/.venv/bin/python" && -x "$CURRENT/.venv/bin/gunicorn" ]]
[[ "$(stat -c '%U:%G' "$CURRENT")" == "root:root" ]]
[[ "$(stat -c '%U:%G' /var/lib/fieldmouse)" == "fieldmouse:fieldmouse" ]]
[[ "$(stat -c '%U:%G' /var/log/fieldmouse)" == "fieldmouse:fieldmouse" ]]
[[ "$(stat -c '%a %U:%G' /etc/fieldmouse/station.toml)" == "640 root:fieldmouse" ]]

echo "3/8 Validating service enablement and activity..."
for unit in "${SERVICES[@]}" "${TIMERS[@]}"; do
    systemctl is-enabled --quiet "$unit"
    systemctl is-active --quiet "$unit"
done

echo "4/8 Validating unit execution context..."
for unit in "${SERVICES[@]}"; do
    [[ "$(systemctl show -p User --value "$unit")" == "fieldmouse" ]]
    [[ "$(systemctl show -p Group --value "$unit")" == "fieldmouse" ]]
    [[ "$(systemctl show -p WorkingDirectory --value "$unit")" == \
        "/opt/project-field-mouse/current" ]]
    systemctl show -p Environment --value "$unit" | grep -q \
        "PFM_CONFIG=/etc/fieldmouse/station.toml"
done
systemctl show -p ExecStart --value fieldmouse-dashboard.service |
    grep -q '/opt/project-field-mouse/current/.venv/bin/gunicorn'

echo "5/8 Checking that legacy schedulers are inactive..."
for legacy in fieldmouse-maintenance.timer app-cleanup.timer app-cleanup.service \
    fieldmouse-storage-manager.timer fieldmouse-storage-manager.service; do
    if systemctl is-active --quiet "$legacy" 2>/dev/null; then
        echo "FAIL: legacy unit remains active: $legacy" >&2
        exit 1
    fi
done

echo "6/8 Exercising approved service restart..."
sudo -n /usr/bin/systemctl restart fieldmouse-dashboard.service
systemctl is-active --quiet fieldmouse-dashboard.service

echo "7/8 Validating dashboard and health..."
curl --fail --silent --show-error http://127.0.0.1:8000/health >/dev/null
curl --fail --silent --show-error http://127.0.0.1:8000/ >/dev/null

echo "8/8 Validating backup and reliability timer execution..."
sudo -n /usr/bin/systemctl start fieldmouse-backup.service
systemctl is-failed --quiet fieldmouse-backup.service && {
    echo "FAIL: on-demand backup failed." >&2
    exit 1
}
sudo -n /usr/bin/systemctl start fieldmouse-reliability.service
systemctl is-failed --quiet fieldmouse-reliability.service && {
    echo "FAIL: on-demand reliability sample failed." >&2
    exit 1
}
[[ -s /var/log/project-field-mouse-reliability/latest.json ]]

echo "Production validation passed for: $CURRENT"
