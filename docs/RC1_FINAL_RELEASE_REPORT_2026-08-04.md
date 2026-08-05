# Project Field Mouse v1.0.0 RC1 Final Release Report

Date: 2026-08-04

Candidate: `54c995065189`

Production release: `rc1-final-54c995065189`

Recommendation: **APPROVE RC1**

## Deployment summary

The candidate was deployed to `project-field-mouse-001` using the normal
transactional deployer. Both deployment utilities were restored from the
candidate, confirmed as executable LF-terminated Bash scripts, and their help
commands completed successfully before deployment.

The deployer installed BirdNET 0.2.16, passed application, configuration, and
BirdNET import preflights twice, confirmed the migration history was current,
and activated the candidate. Rollback capability remains available through:

- previous release: `/opt/project-field-mouse/releases/rc1-final-898778c258f1-b`
- backup: `/var/lib/fieldmouse/backups/predeploy-rc1-final-54c995065189.zip`
- rollback command: `sudo /usr/local/sbin/pfm-rollback`

## Acceptance results

| Area | Result | Evidence |
| --- | --- | --- |
| Transactional deployment | PASS | Deployer exit 0; current symlink points to the candidate |
| Recorder | PASS | Enabled, active, zero restarts; multiple new 5,760,044-byte WAV files completed |
| BirdNET | PASS | Enabled, active, zero restarts; live recordings processed and one new detection saved |
| Dashboard | PASS | Gunicorn active with zero restarts |
| Overview | PASS | HTTP 200 |
| Activity | PASS | HTTP 200; current detection count exposed by dashboard metrics |
| Life List | PASS | HTTP 200 |
| Species | PASS | Known Black-capped Chickadee page HTTP 200 |
| Device | PASS | HTTP 200 using deployed `/var/lib/fieldmouse` paths |
| Health | PASS | HTTP 200, overall `ok`, no warnings |
| Metrics | PASS | HTTP 200 with current recording/detection counts and timing data |
| Audio playback | PASS | Recording 18270 HTTP 200, correct WAV metadata |
| Audio seeking | PASS | Range request returned HTTP 206 and bytes 0–1023 |
| SQLite | PASS | Health integrity check `ok`; database remained readable and writable |
| Cleanup | PASS | Timer enabled/waiting; last applied job exited 0 and completed safely |
| systemd state | PASS | No failed units; candidate services have zero restarts |
| Rollback readiness | PASS | Previous release and verified pre-deployment backup retained |

## BirdNET timestamp reliability

Real production recording 18270, which had previously failed timestamp
parsing, was processed twice with the fixed candidate code. Both executions
reported one saved detection. The final database state remained exactly one
detection with normalized numeric offsets `start_time=18.0` and
`end_time=21.0`. This validates parsing, persistence, and duplicate prevention.

After final activation, recordings 18384 and 18385 completed and were processed
normally. Recording 18385 added one new detection. Across the observation
window, metrics advanced from 2,855 to 2,858 recordings and from 1,037 to 1,038
detections. The BirdNET service restart count remained zero, and the journal
contained no timestamp, traceback, exception, failure, or error entries after
activation.

## Operational observations

- SQLite database size: 4,935,680 bytes
- Mean BirdNET execution: 4,589.43 ms over 1,250 samples
- BirdNET RSS: approximately 218 MB
- Dashboard RSS: approximately 64 MB across Gunicorn master and worker
- Recorder/adaptive scheduler RSS: approximately 36 MB during capture
- System memory utilization: 68.7% during active inference/capture
- CPU load average: 0.12 / 1.24 / 1.08
- CPU temperature: 58.4 C
- Root filesystem: 17 GB free, 70% used
- Cleanup: last result successful; next timer invocation scheduled

The service switch generated orderly SIGTERM shutdown messages. An in-progress
ALSA capture was terminated during the transactional switch and logged as a
failed cycle, but the adaptive recorder shut down cleanly and immediately
resumed under the candidate. This is expected cutover behavior and did not
produce a crash loop.

## Known issues and remaining gates

1. **Medium — production soak incomplete.** Keep the candidate active for the
   planned 12–24 hours, then verify zero restarts, stable resource use, expected
   storage growth, and no timestamp failures before promotion.
2. **Medium — final reboot acceptance pending.** Prior boot recovery validation
   passed, and all candidate units are enabled, but the final deployed commit
   has not yet been reboot-tested. Perform this before tagging.
3. **Low — rare-species cleanup fails closed when rarity cannot be determined.**
   This preserves data rather than deleting uncertain recordings, so it is not
   a release blocker; monitor storage growth.
4. **Low — browser visual acceptance pending.** HTTP rendering and asset-backed
   routes pass, but mobile/desktop visual review and JavaScript-console review
   remain release-owner acceptance tasks.

## Final recommendation

**APPROVE RC1.** The timestamp reliability blocker is cleared, the candidate is
deployed transactionally, the end-to-end recording and detection path is
functioning, SQLite remains healthy, and no service restarted unexpectedly.
The production soak, reboot recovery, administrative preparation, and release
owner review subsequently completed successfully. RC1 is approved for merge,
tagging as `v1.0.0-rc1`, and publication.
