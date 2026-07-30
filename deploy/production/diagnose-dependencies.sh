#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
    echo "Usage: diagnose-dependencies.sh REQUIREMENTS OUTPUT_DIRECTORY" >&2
}

[[ $# -eq 2 ]] || { usage; exit 2; }
readonly REQUIREMENTS="$(realpath "$1")"
readonly OUTPUT="$(realpath -m "$2")"
readonly VENV="$OUTPUT/venv"
readonly TEMP="$OUTPUT/tmp"
readonly CACHE="$OUTPUT/cache"
readonly LOG="$OUTPUT/install.log"
readonly RESOURCES="$OUTPUT/resources.tsv"
readonly SUMMARY="$OUTPUT/summary.txt"

[[ -f "$REQUIREMENTS" ]] || {
    echo "Requirements file not found: $REQUIREMENTS" >&2
    exit 2
}
[[ ! -e "$OUTPUT" ]] || {
    echo "Output already exists: $OUTPUT" >&2
    exit 2
}

mkdir -p "$OUTPUT" "$TEMP" "$CACHE"
{
    echo "=== before ==="
    date -u +%Y-%m-%dT%H:%M:%SZ
    uname -a
    python3 --version
    df -h / "$OUTPUT" /tmp /var/tmp
    df -i / "$OUTPUT" /tmp /var/tmp
    free -h
    cat /proc/swaps
    echo "requirements=$REQUIREMENTS"
} >"$SUMMARY"

printf 'timestamp\tavailable_ram_kib\tswap_free_kib\tdisk_free_kib\ttmp_bytes\tvenv_bytes\n' \
    >"$RESOURCES"

sample_resources() {
    local available swap_total swap_used swap_free disk_free tmp_bytes venv_bytes
    available="$(awk '/^MemAvailable:/{print $2}' /proc/meminfo)"
    read -r swap_total swap_used < <(
        awk 'NR > 1 {total += $3; used += $4} END {print total + 0, used + 0}' /proc/swaps
    )
    swap_free=$((swap_total - swap_used))
    disk_free="$(df --output=avail "$OUTPUT" | tail -n 1 | tr -d ' ')"
    tmp_bytes="$(du -sb "$TEMP" 2>/dev/null | cut -f1 || echo 0)"
    venv_bytes="$(du -sb "$VENV" 2>/dev/null | cut -f1 || echo 0)"
    printf '%s\t%s\t%s\t%s\t%s\t%s\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$available" "$swap_free" \
        "$disk_free" "$tmp_bytes" "$venv_bytes" >>"$RESOURCES"
}

python3 -m venv "$VENV"
started_epoch="$(date +%s)"
echo "started=$(date -u +%Y-%m-%dT%H:%M:%SZ)" >>"$SUMMARY"
echo "phase=pip" >>"$SUMMARY"

set +e
TMPDIR="$TEMP" PIP_CACHE_DIR="$CACHE" \
    "$VENV/bin/python" -m pip install \
    --disable-pip-version-check --progress-bar off --verbose \
    --requirement "$REQUIREMENTS" >"$LOG" 2>&1 &
pip_pid=$!
while kill -0 "$pip_pid" 2>/dev/null; do
    sample_resources
    sleep 10
done
wait "$pip_pid"
exit_code=$?
set -e

sample_resources
completed_epoch="$(date +%s)"
printf '%s\n' "$exit_code" >"$OUTPUT/exit-code"
{
    echo "exit_code=$exit_code"
    echo "elapsed_seconds=$((completed_epoch - started_epoch))"
    echo "completed=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "venv_bytes=$(du -sb "$VENV" | cut -f1)"
    echo "tmp_bytes=$(du -sb "$TEMP" | cut -f1)"
    echo "cache_bytes=$(du -sb "$CACHE" | cut -f1)"
    echo "=== after ==="
    date -u +%Y-%m-%dT%H:%M:%SZ
    uname -a
    python3 --version
    df -h / "$OUTPUT" /tmp /var/tmp
    df -i / "$OUTPUT" /tmp /var/tmp
    free -h
    cat /proc/swaps
} >>"$SUMMARY"

exit "$exit_code"
