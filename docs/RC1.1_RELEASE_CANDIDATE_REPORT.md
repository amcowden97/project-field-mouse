# RC1.1 Release Candidate Report

Date: 2026-08-16 PDT / 2026-08-17 UTC  
Integration branch: `integration/rc1.1`  
Deployed application candidate: `396d740715bc2ecc62bfe2abb0a4194e2baf0fd0`  
GitHub Actions: [run 32001480439](https://github.com/amcowden97/project-field-mouse/actions/runs/32001480439)

## Integration Summary

The candidate contains all HQ-approved RC1.1 initiatives:

- Dashboard V2 and its wildlife polish.
- Experience Initiative Phase 1.
- Verification V2 and the BirdNET-only fallback.
- Reliability Observation Framework.
- Performance and Scalability improvements.
- Open Source Readiness improvements.

The branch was based on canonical `master` at `074f895`. Dashboard V2 and Verification
V2 were originally merged in `d41532a` and `029ff26`. The remaining Dashboard Wildlife
Polish and Experience work was merged in `d36058c`, and the Reliability Observation
history was merged in `2050286`.

The performance work was retained as `729005f`, including migration
`0005_detection_time_indexes.sql`, its idempotency assertions, profiler, measurements,
and audit. Open-source readiness was retained as `b1cc608` without production behavior
changes.

One merge conflict occurred in `tests/test_dashboard_v2.py`. It was resolved by keeping
both sides: the existing persisted-verification/BirdNET-fallback coverage and the new
weekly-activity/species-profile coverage. No functionality or test intent was removed.

Production validation identified one integration defect: Dashboard V2 queried the
obsolete `fieldmouse-storage-manager.timer` name and displayed cleanup as unavailable.
Commit `396d740` changes the Device page to query the deployed
`fieldmouse-cleanup.timer`, updates its explanatory text, and adds a regression test.
This was a compatibility correction, not a feature addition.

## Validation Results

### Automated checks

The exact deployed commit passed the canonical GitHub Actions workflow:

- Development dependency installation: **PASS**.
- Ruff (`app`, `tests`): **PASS**.
- Full Pytest suite: **PASS**.
- Python compileall (`app`): **PASS**.
- `git diff --check`: **PASS** before publication.

The local Windows Python shim was unavailable and the WSL base environment did not
contain test dependencies. No partial local environment was treated as authoritative;
the clean repository CI environment supplied the release-candidate result.

### Database

- Migration 0005 applied successfully during the first transactional deployment.
- The corrected deployment reported `Database is current`.
- Ordered/idempotent migration coverage for versions 1 through 5 passed in CI.
- Production SQLite integrity: **ok**.
- Failed recordings: **0**.
- Database remained readable throughout both transactional switches.

### Dashboard, APIs, and media

The following production paths passed after activation:

- Overview `/`: **PASS**.
- Activity `/activity`: **PASS**.
- Life List `/life-list`: **PASS**.
- Known species `/species/Mallard`: **PASS**.
- Device `/device`: **PASS**.
- Dashboard API `/api/dashboard`: **PASS**.
- Health `/health`: **PASS**.
- Metrics `/api/metrics`: **PASS**.
- Audio playback: **PASS**.
- HTTP byte-range audio seeking: **PASS**.

The Device page now reports the actual cleanup timer. Dashboard rendering retained the
wildlife-first hierarchy, Verification V2 evidence, and honest BirdNET-only fallback.
Existing API paths and response compatibility were preserved.

### Reliability and performance

- Reliability timer: active, enabled, and automatically sampling every five minutes.
- Reliability service: bounded oneshot, completing successfully.
- Recorder, BirdNET, and dashboard restart counts: **0**.
- Queue depth: **0**.
- No failed systemd units.
- Performance migration indexes are present through schema version 5.
- Synthetic evidence at 100,000 detections reports median improvements of 60% for
  Activity, 39% for Overview, 77% for Metrics, and 20% for the Dashboard API.
- Pi BirdNET average during the initial corrected-candidate window: approximately
  7.8 seconds, within the recording cadence.

## Production Deployment

The release was built from a Git archive of the exact CI-approved commit. Archive
SHA-256:

`217573e2810d0714b61e5f575d2134d980b2800adac29fcb03909e5766a4a108`

The standard transactional deployer:

- verified the pinned BirdNET package and runtime imports;
- created an isolated release environment;
- confirmed migration state;
- installed and enabled application services and timers;
- atomically switched the active release;
- completed health validation; and
- retained automatic rollback artifacts.

Production state at the soak baseline:

- Current: `/opt/project-field-mouse/releases/rc1.1-rc-396d740`.
- Previous: `/opt/project-field-mouse/releases/rc1.1-rc-2050286`.
- Verified database backup:
  `/var/lib/fieldmouse/backups/predeploy-rc1.1-rc-396d740.zip`.
- Recorder, BirdNET, dashboard: active/running with zero restarts.
- Cleanup, backup, and reliability timers: active and enabled.
- Health status: `ok`, no warnings.
- Queue depth: 0.
- Recording count increased from 16,216 before integration deployment to 16,238 after
  corrected activation and initial observation.
- Detection count remained 3,310 during this short window; completed recordings did
  not contain qualifying detections.

### Initial resource baseline

- Temperature: 50.7-54.9 C.
- Memory: approximately 40-54% used during post-deployment sampling.
- Swap: 178 MiB used of 989 MiB.
- Root storage: 84.6% used, approximately 8.3 GiB free.
- Dashboard, recorder, and BirdNET remained responsive while telemetry sampled.

Reliability samples around each transactional switch correctly recorded transient
service-unavailable, swap-growth, root-disk-growth, and BirdNET-RSS-growth deltas. These
correspond to intentional service stops and creation of two isolated TensorFlow release
environments. The next scheduled normal-operation sample completed with
`anomalies: []`, confirming that these interval deltas settled after deployment.

## Production Soak

The structured production soak began with commit `396d740` active. Monitor:

- service `NRestarts` and error journals;
- queue depth and oldest pending work;
- recorder and BirdNET throughput;
- health and dashboard availability;
- reliability samples and anomaly recurrence;
- temperature, CPU, RSS, memory, and swap trends; and
- storage growth and cleanup execution.

## Known Issues

### Release blockers

None identified at soak start.

### Minor follow-up

- Complete the structured unattended soak and review telemetry trends before final
  RC1.1 publication approval.
- Root storage is at 84.6% because the active and rollback release environments are
  intentionally retained. Monitor cleanup and storage during the soak; do not remove
  the current rollback target.
- Complete a physical narrow-phone review if it has not already been performed; the
  automated headless environment has a 500-pixel minimum layout viewport.

### Long-term enhancements

- Calibrate Verification V2 only after reviewed field observations are available.
- Add route-latency, queue-age, database-lock, WAL, cleanup-duration, and file-descriptor
  telemetry when justified by production evidence.
- Consider deeper-page keyset pagination or summary tables only if future production
  traces confirm the synthetic scaling limits.
- Complete repository-owner settings and branding improvements listed in the Open
  Source Readiness report.

## Final Recommendation

**READY WITH MINOR FOLLOW-UP**

All approved RC1.1 work is integrated, clean CI passes, database compatibility is
preserved, the corrected candidate is active on the Raspberry Pi, rollback remains
available, and the structured production soak has begun. No current evidence indicates
a release-blocking application or data-integrity defect. Final public release approval
should follow the unattended soak and review of recurring telemetry and storage trends.
