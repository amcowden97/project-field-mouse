# Changelog

This project follows Semantic Versioning. Release entries are generated from Git
history with `python scripts/changelog.py VERSION --since PREVIOUS_TAG`, then curated
for users before tagging.

## 1.1.0 - Unreleased

### Added

- Wildlife-first Dashboard V2 stories, responsive layouts, species field notes,
  confidence filtering, and verification-ready disclosures.
- Verification V2 rule engine, modular evidence providers, explainable consensus,
  persistence, review support, and safe BirdNET-only fallback.
- Reliability sampling and diagnostic snapshots for application resources, queue,
  storage growth, thermal state, timers, and service restarts.
- Functional health freshness for recordings, BirdNET processing, detections, queue,
  and cleanup.
- Graduated storage watermarks, daily-growth forecasting, estimated time/date to full,
  optional state-change webhook notifications, and emergency recovery.
- Transactional release pruning that retains the current release, previous rollback,
  and one inactive release.

### Changed

- Detection-time indexes improve Overview, Activity, metrics, and dashboard API queries.
- Dashboard copy presents detector confidence and independent verification honestly.
- Cleanup can expire eligible audio while preserving database observation history and
  can recover the recorder after an ENOSPC event.
- Production reliability sampling loads the same centralized station configuration as
  the other services.
- Installation, deployment, open-source, and operational documentation reflect the
  RC1.1 production model.

### Fixed

- Device status queries the deployed `fieldmouse-cleanup.timer` unit.
- Reliability telemetry no longer falls back to an immutable release-local recordings
  directory under systemd.
- Release environments are bounded so inactive virtual environments cannot consume the
  entire root filesystem.

### Upgrade notes

- Back up and verify SQLite before deployment.
- Use the transactional deployer and refresh production systemd/configuration files.
- Verify schema migrations 1 through 5 exactly once, then validate health, metrics,
  playback, cleanup, reliability sampling, and one full recording/detection cycle.
- Keep rollback artifacts until the production soak is accepted.

## 1.0.0-rc1 - 2026-08-05

### Added

- Dashboard V3 overview, activity, Life List, species, and device experiences.
- Evidence-driven bird verification, review workflow, calibration, and evaluation tools.
- Central configuration, safe database migrations, backups, health checks, metrics,
  deployment services, simulator, and unified `pfm` CLI.

### Changed

- Dashboard V3 now serves the established dashboard URLs without breaking bookmarks.
- Infrastructure and verification database changes share one ordered migration history.
- Station identity, storage, BirdNET, recorder, cleanup, dashboard, health, and logging
  settings are loaded from `config/station.toml` with `PFM_*` overrides.

### Upgrade notes

- Back up the SQLite database before upgrading.
- Run `python -m app.cli migrate` before starting the services.
- Reinstall systemd units and verify the health endpoint after restart.
- This is a release candidate. Continue monitoring service health, resource use,
  and storage growth during normal production operation.
