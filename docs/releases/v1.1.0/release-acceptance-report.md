# RC1.1 Release Acceptance Report

Date opened: 2026-08-19 PDT  
Candidate: `fb9b131548c1dd4e2691c98490a7ddfc58860573`  
Release-package commit: `99eed1534977c1672dcdbbe00fd48fa51d76c9b2`  
Target version: `v1.1.0`  
Status: **HOLD — minimum production soak is still in progress**

## Executive summary

The final candidate was activated at 2026-08-18 23:51:35 PDT using the transactional
deployer. At the 12-hour 27-minute checkpoint, the recorder, BirdNET worker, dashboard,
cleanup, reliability telemetry, database, and dashboard routes were healthy. No service
restart, queue accumulation, failed recording, database corruption, or core-service
warning was observed.

This is not yet a release approval. The minimum 24-hour window completes at
approximately 2026-08-19 23:51 PDT. A controlled reboot and post-reboot recording cycle
must follow the uninterrupted soak. The storage forecast also requires review at the
24-hour point to confirm that scheduled retention establishes the expected steady state.

## Deployment summary

- Deployment duration: 7 minutes 2 seconds.
- Active release: `/opt/project-field-mouse/releases/rc1.1.1-fb9b131`.
- Previous rollback: `/opt/project-field-mouse/releases/rc1.1.1-4e74b15`.
- One additional inactive release retained according to policy.
- Verified predeployment backup:
  `/var/lib/fieldmouse/backups/predeploy-rc1.1.1-fb9b131.zip`.
- Database migrations: versions 1 through 5, unchanged by the hardening patch.
- Transactional deployment and startup preflights: pass.
- Working release commit and pinned BirdNET package validation: pass.

## Operational validation

### Freshness and throughput

At 2026-08-19 12:18 PDT:

- Recorder freshness: healthy; latest recording age approximately 90 seconds.
- BirdNET freshness: healthy; latest processed recording age approximately 90 seconds.
- Detection freshness: healthy; latest detection age approximately 516 seconds.
- Queue depth: 0.
- Failed recordings: 0.
- Recordings: 18,677, an increase of 728 from the immediate post-deployment baseline.
- Detections: 3,747; 227 detections during the preceding 24 hours.
- BirdNET mean execution time: 4,424.5 ms across 847 samples.

### Services and telemetry

- Recorder: active, zero restarts.
- BirdNET worker: active, zero restarts.
- Dashboard: active, zero restarts.
- Failed systemd units: zero.
- Reliability timer: active and sampling approximately every five minutes.
- Settled reliability samples: no anomalies.
- Recorder/BirdNET/dashboard warnings since activation: none.
- Temperature at checkpoint: 55.6 °C.
- Memory available: approximately 503 MB; health reported 51.6% used.

### Storage and cleanup

- Initial post-deployment disk state: 70% used, approximately 17 GB available.
- 12-hour checkpoint: 75.3% used, approximately 14.3 GB available.
- Forecast growth: approximately 8.12 GB/day.
- Estimated time to full at checkpoint: approximately 42.3 hours.
- Health storage state: normal; advisory begins at 80%.
- Scheduled cleanup at 05:36 PDT expired 187 eligible audio files, reclaimed
  approximately 1.0 GB, and preserved all 187 database rows.
- Scheduled cleanup at 11:43 PDT completed successfully with no eligible recordings.
- Cleanup did not interrupt recording or BirdNET processing.

The forecast is functioning as designed, but the current gross trajectory is not yet
release-acceptance evidence. The 24-hour review must show that retention and emergency
controls keep sufficient headroom as recordings cross their configured age thresholds.

### Health and dashboard

- `/health`: HTTP 200, status `ok`, SQLite integrity `ok`.
- `/api/metrics`: HTTP 200.
- `/`: HTTP 200, approximately 90 ms at the checkpoint.
- `/activity`: HTTP 200, approximately 22 ms.
- `/life-list`: HTTP 200, approximately 39 ms.
- `/species/Mallard`: HTTP 200, approximately 9 ms.
- `/device`: HTTP 200, approximately 64 ms.
- `/api/dashboard`: HTTP 200, approximately 17 ms.
- Full audio playback and HTTP range seeking passed immediate post-deployment validation.

### Notifications

The off-device webhook is not configured. HQ classifies it as recommended but optional.
Webhook-disabled configuration loads successfully, no secret is logged, and local
health, forecasting, telemetry, cleanup, and recovery operate without it.

## Regression validation

- Candidate CI run `32224121200`: pass.
- Release-package CI run `32226974927`: pass.
- SQLite integrity: pass.
- Dashboard and APIs: pass at interim checkpoint.
- Recording and BirdNET pipelines: pass at interim checkpoint.
- Playback and seeking: pass immediately after deployment.
- Cleanup and history preservation: pass.
- Release retention and rollback availability: pass.
- Controlled reboot and post-reboot recording cycle: **pending after soak**.

## Known limitations accepted for v1.1.0

- Verification weights remain conservative until reviewed field observations support
  calibration.
- Rare-species cleanup fails closed when rarity cannot be determined.
- Off-device webhook notification is optional and disabled by default.
- Weather content remains a non-live placeholder.
- The dashboard is intended for a trusted local network unless protected by an
  operator-managed authenticated reverse proxy.

## Final decision gates

- [ ] At least 24 continuous hours completed.
- [ ] Final storage/forecast/cleanup trajectory accepted.
- [ ] No P0 or P1 defects found in the full window.
- [ ] Controlled reboot passes.
- [ ] Services automatically recover with zero unexpected restarts.
- [ ] A post-reboot recording is processed and dashboard-visible.
- [ ] Final SQLite integrity check returns `ok`.
- [ ] HQ explicitly approves public release.

## HQ recommendation

**HOLD.** The evidence is positive, but the mandatory observation interval and reboot
validation are incomplete. Do not merge, tag, publish, or update the website until all
gates above are checked and HQ approves release.
