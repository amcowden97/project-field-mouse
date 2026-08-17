# Operations and API

`GET /health` returns JSON and HTTP 200 when healthy or 503 when degraded. It covers
CPU, RAM, disk, temperature, database integrity, failed recordings, microphone tools,
network interfaces, uptime, and configured services.

```bash
python -m app.system.health_check --pretty
systemctl status fieldmouse-recorder fieldmouse-birdnet fieldmouse-dashboard
journalctl -u fieldmouse-recorder --since today
python -m app.database.maintenance check
arecord -l
systemctl list-timers fieldmouse-backup.timer fieldmouse-cleanup.timer \
  fieldmouse-reliability.timer
```

Application logs are JSON lines under `logs/`, rotate at 5 MB by default, and retain
five archives. If disk is high, dry-run cleanup, inspect candidates, back up, then
apply. Never delete a live SQLite WAL or SHM file.

Other endpoints are `GET /api/dashboard` and range-capable
`GET /audio/<recording_id>`. The audio endpoint is confined to the recordings tree.
`GET /api/metrics` exposes database size, queue depth, recording/detection/failure
counts, daily detections, and collected execution timings. There is no write API.

## Reliability telemetry

`fieldmouse-reliability.timer` records one bounded sample every five minutes under
`/var/log/project-field-mouse-reliability/`. Daily `metrics-YYYY-MM-DD.jsonl` files retain
30 days of CPU, load, memory, swap, disk and network I/O counters, Pi power/thermal
flags, and service process-tree RSS, swap, threads, descriptors, CPU time, and
restart counts. It also records recorder/database/log growth, filesystem error
counters, and backup/cleanup timer results. `latest.json` is the most recent complete
sample.

Objective abnormal conditions create `diagnostic-*.json` snapshots containing the
sample, top processes, kernel warnings, and the last 100 journal lines for each
long-running service. Snapshots are capped at 20. Collection never restarts or
signals an application service.

```bash
sudo -n /usr/bin/systemctl start fieldmouse-reliability.service
/opt/project-field-mouse/current/.venv/bin/python \
  -m app.system.reliability_monitor --summarize
sudo -n /usr/bin/journalctl --no-pager -n 200 \
  -u fieldmouse-reliability.service
```

If the station becomes slow but remains reachable, do not reboot until the latest
metrics and diagnostic snapshots have been copied for analysis. If it is entirely
unreachable, record the exact time, whether link/activity LEDs remain active, and
whether local console input works before power cycling. This distinguishes a
network-only loss from an operating-system or power failure.

The production image currently uses volatile systemd journal storage. Reliability
JSONL and triggered diagnostic snapshots persist, but journal messages produced
after the final sample and before a hard power cycle do not. Enabling a bounded
persistent system journal is a separate, explicitly reviewed operational change.
