# Changelog

This project follows Semantic Versioning. Release entries are generated from Git
history with `python scripts/changelog.py VERSION --since PREVIOUS_TAG`, then curated
for users before tagging.

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
