# 3.0.0 RC1 release checklist

Record evidence and operator initials for every item. Do not promote RC1 when a
required item fails.

- [ ] Fresh install completes on a Raspberry Pi 5.
- [ ] Database backup verifies and migrations complete.
- [ ] Recorder creates a valid WAV file using the configured device.
- [ ] BirdNET processes the WAV and stores at least one detection.
- [ ] Overview, Activity, Life List, Species, and Device pages return HTTP 200.
- [ ] Audio playback supports seeking and returns the expected WAV.
- [ ] `/health` returns HTTP 200 and `/api/metrics` returns current metrics.
- [ ] Recorder, BirdNET, and dashboard services are enabled and active.
- [ ] Failed service processes restart without entering a crash loop.
- [ ] Maintenance timer is enabled; a dry run and an applied cleanup behave correctly.
- [ ] SIGTERM produces graceful shutdown and clean logs.
- [ ] SQLite `PRAGMA integrity_check` returns `ok`.
- [ ] Reboot restores all services and recording/detection processing.
- [ ] Mobile and desktop browser checks show no broken links or missing assets.
- [ ] CPU, memory, storage growth, page latency, and BirdNET latency are recorded.
- [ ] Known issues in `RELEASE_NOTES.md` are accepted by the release owner.
- [ ] Tag `v3.0.0-rc1` points at the approved integration commit.
