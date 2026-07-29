# Repository and security audit

## Addressed

- One typed configuration model covers station, audio, storage, BirdNET, dashboard,
  logging, health, retention, filters, files, environment overrides, and defaults.
- SQLite gained WAL, busy timeout, composite indexes, integrity checks, online backup,
  and validated atomic restore.
- Health monitoring, rotating structured logs, hardened systemd units, CI, tests, and
  install/update/repair/verify commands provide a production baseline.
- File serving uses resolved-path containment. Subprocesses use argument arrays and
  timeouts without a shell.

## Remaining debt

1. `app/web/app.py` mixes queries, OS probes, and routes; extract repositories after
   Dashboard V3 stabilizes.
2. `status_dashboard.py` and `adaptive_scheduler.py` still parse TOML independently.
3. Two storage-cleanup implementations duplicate policy; retire the older one after a
   compatibility release.
4. Move `dashboard-v1-archive` out of the product tree.
5. Split direct dependencies from the ML transitive lock and test an ARM64 lock.
6. The migration ledger needs an ordered runner before the next schema change.
7. Add durable service/failure events once BirdNET failure semantics stabilize.
8. No LICENSE file is committed. The copyright owner must choose and add an
   OSI-approved license before describing the repository as open source; this release
   does not guess the owner's legal intent.

## Security findings

- Dashboard traffic has no authentication or TLS. Restrict it to a trusted LAN and use
  a TLS/authenticating reverse proxy before internet exposure.
- Coordinates and station metadata are sensitive. Use approximate public locations,
  mode `0640` for config/backups, and explicit consent before upload.
- Units run unprivileged with filesystem protection; grant only the `audio` group.
- Continue parameterized SQL, allowlisted sort fields, and path containment.
- Add dependency and secret scanning when the GitHub security policy is finalized.

Measure CPU, RSS, queue depth, latency, and writes for 24 hours before tuning. Keep one
BirdNET worker and one threaded web process on Pi until measurements justify more.
