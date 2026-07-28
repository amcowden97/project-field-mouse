#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

GREEN="\033[0;32m"
BLUE="\033[0;34m"
RED="\033[0;31m"
YELLOW="\033[1;33m"
RESET="\033[0m"

title() {

    echo
    echo -e "${BLUE}========================================${RESET}"
    echo -e "${BLUE}$1${RESET}"
    echo -e "${BLUE}========================================${RESET}"
    echo

}

success() {

    echo -e "${GREEN}✓ $1${RESET}"

}

warning() {

    echo -e "${YELLOW}$1${RESET}"

}

failure() {

    echo -e "${RED}$1${RESET}"

}

enter_project() {

    cd "$PROJECT_ROOT"

}
