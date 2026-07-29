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
systemctl list-timers fieldmouse-maintenance.timer
```

Application logs are JSON lines under `logs/`, rotate at 5 MB by default, and retain
five archives. If disk is high, dry-run cleanup, inspect candidates, back up, then
apply. Never delete a live SQLite WAL or SHM file.

Other endpoints are `GET /api/dashboard` and range-capable
`GET /audio/<recording_id>`. The audio endpoint is confined to the recordings tree.
`GET /api/metrics` exposes database size, queue depth, recording/detection/failure
counts, daily detections, and collected execution timings. There is no write API.
