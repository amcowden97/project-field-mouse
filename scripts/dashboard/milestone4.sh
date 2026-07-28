#!/usr/bin/env bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

source "$SCRIPT_DIR/../lib/common.sh"

title "Dashboard V3 - Milestone 4"

enter_project

success "Project located."

success "Ready for component generation."

echo

echo "Milestone complete."
