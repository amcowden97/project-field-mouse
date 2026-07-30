#!/usr/bin/env bash
set -Eeuo pipefail

[[ "$(uname -s)" == "Linux" ]] || { echo "Installer requires Linux." >&2; exit 1; }
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OPERATOR="${PFM_OPERATOR:-${SUDO_USER:-$USER}}"
RELEASE_ID="${PFM_RELEASE_ID:-install-$(date -u +%Y%m%dT%H%M%SZ)}"

sudo "$ROOT/deploy/production/bootstrap-production.sh" "$OPERATOR"
sudo /usr/local/sbin/pfm-deploy --source "$ROOT" --release-id "$RELEASE_ID"

echo "Installation complete. Start a new login session before using passwordless commands."
