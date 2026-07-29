#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REVISION="$(git -C "$ROOT" rev-parse --short=12 HEAD)"
RELEASE_ID="${PFM_RELEASE_ID:-update-$(date -u +%Y%m%dT%H%M%SZ)-$REVISION}"

sudo -n /usr/local/sbin/pfm-deploy --source "$ROOT" --release-id "$RELEASE_ID"
