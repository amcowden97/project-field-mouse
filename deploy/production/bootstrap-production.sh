#!/usr/bin/env bash
set -Eeuo pipefail

[[ $EUID -eq 0 ]] || {
    echo "Run once as root: sudo deploy/production/bootstrap-production.sh USER" >&2
    exit 1
}
OPERATOR="${1:-}"
[[ "$OPERATOR" =~ ^[a-z_][a-z0-9_-]*[$]?$ ]] || {
    echo "Usage: bootstrap-production.sh EXISTING_USER" >&2
    exit 2
}
id "$OPERATOR" >/dev/null
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

apt-get update
apt-get install -y python3-venv rsync curl alsa-utils libsndfile1

for command in python3 rsync curl flock runuser visudo arecord; do
    command -v "$command" >/dev/null || {
        echo "Missing required command: $command" >&2
        exit 1
    }
done
getent group pfm-operators >/dev/null || groupadd --system pfm-operators
usermod -a -G pfm-operators "$OPERATOR"
id fieldmouse >/dev/null 2>&1 ||
    useradd --system --home /var/lib/fieldmouse --shell /usr/sbin/nologin fieldmouse
usermod -a -G audio fieldmouse

install -o root -g root -m 0755 "$ROOT/deploy/production/pfm-deploy" \
    /usr/local/sbin/pfm-deploy
install -o root -g root -m 0755 "$ROOT/deploy/production/pfm-rollback" \
    /usr/local/sbin/pfm-rollback
TEMP_POLICY="$(mktemp /etc/sudoers.d/project-field-mouse.XXXXXX)"
trap 'rm -f "$TEMP_POLICY"' EXIT
install -o root -g root -m 0440 "$ROOT/deploy/sudoers/project-field-mouse" "$TEMP_POLICY"
visudo -cf "$TEMP_POLICY"
mv "$TEMP_POLICY" /etc/sudoers.d/project-field-mouse
trap - EXIT
visudo -c

echo "Bootstrap complete. $OPERATOR must start a new login session for group membership."
echo "Then validate: sudo -n true"
echo "Deploy with: sudo -n /usr/local/sbin/pfm-deploy --source $ROOT"
