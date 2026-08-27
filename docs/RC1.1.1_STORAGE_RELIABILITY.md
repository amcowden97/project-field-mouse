# RC1.1.1 storage reliability patch

This patch responds to the 2026-08-18 production recording outage without changing
detectors, verification, scientific behavior, or the Dashboard V3 experience.

## Storage watermarks

| Root usage | State | Behavior |
|---:|---|---|
| below 80% | Normal | Normal operation |
| 80% | Advisory | Health/dashboard data exposes the advisory and forecast; release health is not blocked |
| 90% | Warning | Health becomes degraded and reliability diagnostics are captured |
| 95% | Critical | Immediate policy cleanup is attempted |
| 98% | Emergency | Backup timer is suspended, cleanup is attempted, and recording remains prioritized |

These defaults leave about 11.4, 5.7, 2.85, and 1.14 GiB respectively on the
station's 57 GiB root filesystem. A one-minute 48 kHz mono PCM schedule can produce
about 7.7 GiB/day, so 80% provides operator lead time, 90% is actionable, 95%
retains SQLite working space, and 98% is reserved for preservation of capture.
Thresholds are ordered and validated through `[health]` configuration.

Cleanup candidate discovery no longer performs a global grouped query. It uses
bounded, index-friendly `NOT EXISTS` selection for old zero-detection recordings,
so the emergency path can operate under pressure. Detection-bearing recordings
continue to fail closed unless an authoritative rare-species list is configured.
The root reliability service starts the existing cleanup unit; if cleanup succeeds
and the recorder is inactive, it starts the recorder. An emergency-suspended backup
timer resumes after a later sample confirms storage is below critical.

## Functional freshness

`GET /health` and dashboard statistics now distinguish process state from pipeline
progress. They expose:

- latest recording timestamp and age;
- latest BirdNET-completed recording timestamp and age, including recordings with
  zero detections;
- latest detection timestamp and age;
- pending/processing queue depth;
- cleanup result, completion timestamp, and age;
- storage state, thresholds, bytes free, observed bytes/day, seconds remaining, and
  estimated full timestamp.

A running recorder with stale database progress is degraded as `recording stalled`.
A running BirdNET worker with stale processed-recording progress is degraded as
`BirdNET processing stale`. Empty new installations receive an initialization state,
not a false stall.

## Off-device notification

Set `health.notification_webhook_url` (preferably via the
`PFM_HEALTH_NOTIFICATION_WEBHOOK_URL` environment variable) to an HTTPS endpoint
owned by operations. The reliability service sends a versioned JSON POST for state
changes involving:

- critical/emergency storage;
- recording stall;
- BirdNET processing stall;
- cleanup failure or staleness;
- recovery from those conditions.

Payloads include station ID, UTC time, conditions, disk/forecast data, functional
health, and automatic-recovery actions. Notification state is persisted beside the
reliability metrics, preventing repeated five-minute alerts for an unchanged state.
Delivery is best effort with a five-second default timeout; telemetry and recovery
continue if the endpoint is unavailable. Do not commit webhook credentials.

## Release retention

After a candidate passes every deployment and health gate, deployment retains:

1. the active `current` release;
2. the `previous` rollback target;
3. one newest inactive release for diagnosis.

Older inactive environments are removed through
`app.system.release_retention`. It resolves every target, refuses paths outside the
exact releases directory, never follows release symlinks, and is unit tested. No
pruning occurs before a successful cutover.

## Validation

The deterministic low-storage scenario creates an old eligible WAV and SQLite
history, enters critical state, invokes cleanup, preserves the database row, creates
a new processed recording, and verifies:

- policy cleanup reclaimed the eligible audio;
- automatic cleanup completed;
- recorder start/recovery action was available;
- latest recording became fresh;
- BirdNET processed freshness became fresh;
- queue depth returned to zero;
- no reboot or model/verification change was involved.

Production acceptance still requires deploying through the normal transactional
path and observing at least one real cleanup cycle, recording, BirdNET completion,
webhook test event, forecast update, and release-pruning dry-run/result.
