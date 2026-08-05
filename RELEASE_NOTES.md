# Project Field Mouse 1.0.0 RC1

Project Field Mouse 1.0.0 RC1 integrates the infrastructure, bird verification,
and Dashboard V3 milestones into one reviewable release candidate.

## Highlights

- A responsive nature-focused Dashboard V3 across overview, activity, Life List,
  species, and device pages.
- BirdNET detections can be enriched with explainable verification evidence,
  prioritization, review ground truth, calibration, and evaluation reports.
- Centralized TOML/environment configuration, safe SQLite migrations and backups,
  health and metrics endpoints, simulation tools, and hardened systemd units.

## Migration

1. Create and verify a database backup.
2. Install the release requirements in the station virtual environment.
3. Run `python -m app.cli migrate`.
4. Install the units from `deploy/systemd`, reload systemd, and restart the recorder,
   BirdNET worker, dashboard, and maintenance timer.
5. Run `scripts/verify.sh` and complete `docs/releases/rc1/release-checklist.md`.

The integration renumbers verification migrations after infrastructure migrations.
Do not deploy over a database that already ran an unreleased verification migration
without first validating its `schema_migrations` history.

## Known limitations

- Rare-species cleanup fails closed when rarity cannot be determined. This
  preserves uncertain recordings but can increase storage consumption.
- Dashboard V2 assets remain temporarily available as rollback artifacts.
- Weather content is an intentional non-live placeholder.
