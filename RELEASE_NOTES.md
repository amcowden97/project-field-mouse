# Project Field Mouse 1.1.0

Project Field Mouse 1.1.0 turns the original release candidate into a more polished,
observable, and resilient single-station wildlife monitor. It combines the wildlife-
first Dashboard V2 experience, explainable Verification V2 foundations, performance
indexes, reliability telemetry, and the storage hardening proven during production
recovery.

Publication remains conditional on the final production soak and every required item
in the [release checklist](docs/releases/v1.1.0/release-checklist.md).

## Highlights

- A responsive, wildlife-first Overview, Activity journal, Life List, species field
  notes, and detailed Device page.
- Clear BirdNET-only labeling plus explainable Verification V2 evidence when independent
  evidence is available.
- Indexed detection-time queries and bounded dashboard aggregates for larger databases.
- Five-minute reliability samples covering service restarts, process resources, queue
  depth, storage growth, temperature, timers, and functional freshness.
- Graduated storage states at 80%, 90%, 95%, and 98%, with growth forecasting and
  estimated time/date to full.
- ENOSPC-safe cleanup, history-preserving audio expiration, recorder recovery, and
  bounded release retention that preserves the active release and rollback options.

## Dashboard improvements

The Overview now leads with the station's wildlife story rather than system internals.
It includes daily activity, highlights, recent visitors, discoveries, weekly rhythm,
and a compact health summary. Activity supports confidence filters, audio playback,
and verification disclosures. Species pages add observation rhythm, seasonality,
confidence distribution, and recent clips. Navigation and cards adapt to mobile-width
screens while the Device page keeps operational detail available without dominating
the main experience.

## Verification V2

BirdNET remains the primary detector. Verification V2 stores a transparent consensus
derived from configurable, independent evidence sources. Missing or failed verification
providers degrade to an explicit unavailable or BirdNET-only state; they do not invent
support. The initial framework and presentation are ready, but scientific weights have
not been recalibrated without reviewed field observations.

## Performance and reliability

Migration `0005_detection_time_indexes.sql` adds indexes for common time-oriented
detection queries. Reliability telemetry is collected by a bounded systemd timer and
can create diagnostic snapshots without restarting application services. Health now
reports recording, processing, detection, queue, and cleanup freshness in addition to
process state, so a running but stale pipeline is not considered healthy.

The storage hardening adds graduated watermarks, daily-growth forecasting, emergency
cleanup, automatic recorder recovery, and release-directory pruning. Cleanup expires
eligible audio while preserving database history. The deployment process retains the
current release, the previous rollback release, and one inactive release.

## Breaking changes

No public dashboard route, API route, or existing database record format is intentionally
broken. Existing migrations remain ordered and idempotent. Operators installing the
new reliability and cleanup behavior must refresh the production systemd units and
production configuration; copying only the Python package is not a supported upgrade.

## Upgrade notes

1. Create and verify an off-station-capable database backup.
2. Confirm sufficient free space for a transactional release and virtual environment.
3. Use the standard transactional deployer; do not replace `/opt/project-field-mouse/current`
   manually.
4. Confirm migrations 1 through 5 occur exactly once. No new migration is expected from
   the final storage-hardening patch.
5. Reload the supplied systemd units and verify recorder, BirdNET, dashboard, cleanup,
   and reliability timers.
6. Check `/health`, `/api/metrics`, SQLite integrity, audio playback/range requests, and
   a complete new recording/detection cycle.
7. Keep the generated backup and previous release until the post-upgrade observation
   window is accepted.

See [Installation](docs/INSTALLATION.md), [Production deployment](docs/PRODUCTION_DEPLOYMENT.md),
[Operations](docs/OPERATIONS.md), and [Rollback](docs/ROLLBACK.md).

## Known limitations

- Verification V2 calibration remains intentionally conservative until sufficient
  reviewed field observations are available.
- Rare-species cleanup fails closed when rarity cannot be determined. This preserves
  uncertain audio but can reduce reclaimable space.
- Off-device webhook notification is optional and is not configured by default. Local
  health, telemetry, cleanup, and recovery remain functional without it.
- Weather content is a non-live placeholder.
- The dashboard is intended for trusted local networks unless an operator supplies a
  reviewed authenticated reverse proxy.
