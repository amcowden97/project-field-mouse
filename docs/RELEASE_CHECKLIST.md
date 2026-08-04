# 3.0.0 RC1 release checklist

Record evidence and operator initials for every item. Do not promote RC1 when a
required item fails.

- [ ] Fresh install completes on a Raspberry Pi 5.
- [x] Database backup verifies and migrations complete.
- [x] Recorder creates a valid WAV file using the configured device.
- [x] BirdNET processes the WAV and stores at least one detection.
- [x] Overview, Activity, Life List, Species, and Device pages return HTTP 200.
- [x] Audio playback supports seeking and returns the expected WAV.
- [x] `/health` returns HTTP 200 and `/api/metrics` returns current metrics.
- [x] Recorder, BirdNET, and dashboard services are enabled and active.
- [x] Failed service processes restart without entering a crash loop.
- [x] Maintenance timer is enabled; a dry run and an applied cleanup behave correctly.
- [x] SIGTERM produces graceful shutdown and clean logs.
- [x] SQLite `PRAGMA integrity_check` returns `ok`.
- [ ] Reboot restores all services and recording/detection processing.
- [ ] Mobile and desktop browser checks show no broken links or missing assets.
- [x] CPU, memory, storage growth, page latency, and BirdNET latency are recorded.
- [ ] Known issues in `RELEASE_NOTES.md` are accepted by the release owner.
- [ ] Tag `v3.0.0-rc1` points at the approved integration commit.

## 2026-07-29 Raspberry Pi validation evidence

- Static validation at `e04a11b`: 30 tests passed in 0.65 seconds, Ruff passed,
  compileall passed, and `git diff --check` passed.
- A verified live backup was created at
  `data/backups/fieldmouse-project-field-mouse-001-20260729T200324Z.zip`.
- Temporary-database migrations applied versions 1–4 in order. The second run
  was a no-op; foreign keys reported `1`; all station, detection, verification,
  and review schema checks passed; integrity returned `ok`.
- Recording `9813` is a 5,760,044-byte, 60-second, 48 kHz mono PCM WAV. BirdNET
  processed it successfully in an observed 13-second pipeline interval. The
  outdoor sample had zero detections, so the same-recording persistence gate
  remains open. Existing real detections are persisted and playable.
- Overview, Activity, Life List, Black-capped Chickadee Species, Device, Health,
  and Metrics routes returned HTTP 200. Fourteen overview static assets loaded.
  A ranged audio request returned HTTP 206 and bytes 0–1023.
- Dashboard restart readiness was 5.542 seconds. Local overview latency over 20
  requests was 13–33 ms (16.6 ms average).
- BirdNET inference was approximately 3.5–3.7 seconds. A recurring two-FD leak
  caused two `EMFILE` crashes before `e04a11b`; after the fix, descriptors
  remained stable at 6–7 across repeated live inference cycles.
- Recorder, BirdNET, and dashboard crash recovery produced new active PIDs.
  Cleanup dry-run and applied modes found no eligible recordings and preserved
  2,375 database rows and 2,404 WAV files; integrity remained `ok`.
- Resource snapshot: recorder 12 MB RSS, BirdNET 341 MB RSS, dashboard 24 MB
  RSS, system memory 516/990 MB used with 265 MB swap used, CPU load
  0.17/0.35/0.26, temperature 51°C, recordings 13 GB, and 32 GB disk free.
  SQLite test queries averaged 0.005–0.141 ms.

## Open release gates

- Validate a newly recorded WAV that produces and persists at least one detection.
- Run graceful administrative restarts and a reboot recovery test. The SSH
  account does not currently have non-interactive sudo for these operations.
- Complete mobile/desktop visual and JavaScript-console review. HTTP and asset
  checks passed, but headless Chromium did not complete screenshots.
- Resolve deployment drift: the Pi runs legacy `/home/amcowden97` units and
  Flask's development server, while RC1 deployment files target `/opt` and
  Gunicorn. Gunicorn is not installed in the active virtual environment.
- Complete a 12–24 hour soak of the FD fix and review resource/log trends.

## 2026-08-04 final production deployment evidence

- Transactional deployment of commit `54c995065189` completed successfully as
  release `rc1-final-54c995065189`. Runtime preflights passed twice, the
  database was current, and the deployer retained both the previous release
  (`rc1-final-898778c258f1-b`) and verified backup
  `predeploy-rc1-final-54c995065189.zip`.
- Recorder, BirdNET, and dashboard are enabled and active with zero restarts.
  No systemd units are failed. The cleanup timer is enabled and waiting; its
  most recent applied run completed successfully.
- Production health is HTTP 200 with SQLite integrity `ok` and no warnings.
  Metrics is HTTP 200. Overview, Activity, Life List, Species, and Device pages
  all return HTTP 200.
- Audio recording `18270` returns HTTP 200; a bytes 0–1023 seek returns HTTP
  206 with the correct `Content-Range`.
- The previously failed recording `18270` was reprocessed twice. Each run
  reported one saved detection, while SQLite retained exactly one detection
  with normalized offsets `18.0`–`21.0`, confirming idempotency.
- During the post-deployment observation, recording count advanced from 2,855
  to 2,858 and detection count advanced from 1,037 to 1,038. Recordings 18384
  and 18385 completed, and BirdNET stored one new detection for 18385 without
  a timestamp error or worker restart.
- Resource snapshot: BirdNET 218 MB RSS, dashboard workers 64 MB combined RSS,
  recorder/adaptive scheduler approximately 36 MB RSS, system memory 68.7%,
  load average 0.12/1.24/1.08, temperature 58.4 C, and 17 GB free (70% used).
  Metrics reports mean BirdNET execution of 4,589 ms over 1,250 samples and a
  4.94 MB SQLite database.

## Remaining acceptance work after final deployment

- Complete the planned 12–24 hour production soak and review restart counters,
  resource trends, disk growth, and timestamp-related logs.
- Complete the outstanding mobile/desktop visual and JavaScript-console review.
- Obtain release-owner acceptance of the documented known issues before tagging.
- Perform the final reboot recovery check before promoting or tagging RC1.
