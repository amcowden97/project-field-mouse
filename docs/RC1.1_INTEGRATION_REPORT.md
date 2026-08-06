# RC1.1 Integration Candidate 1 Report

Date: 2026-08-06  
Integration branch: `integration/rc1.1`  
Validated candidate: `99ec4a6927b4e3c945db64070173d9441595cbe8`

## Merge Summary

- Created `integration/rc1.1` from canonical `master` at `074f895`.
- Merged `feature/dashboard-v2` in `d41532a`.
- Merged `feature/verification-v2` in `029ff26`.
- Both merges completed without conflicts.
- Added the integration adapter in `99ec4a6` so Dashboard V2 reads persisted Verification V2 evidence while retaining the BirdNET-only fallback when no verification row exists.
- No database migrations were added, removed, or changed. The existing ordered migration history remains versions 1 through 4, and the transactional deployer confirmed the production database is current.
- No verification weights, calibration data, or additional verification modules were introduced.

## Validation

### Automated validation

GitHub Actions run [31120414898](https://github.com/amcowden97/project-field-mouse/actions/runs/31120414898) passed for the integrated candidate:

- Pytest: **PASS** — 75 tests passed in 1.42 seconds.
- Ruff: **PASS** — no findings.
- Compileall: **PASS**.
- Integration tests cover persisted verification evidence and the BirdNET-only fallback.
- Working tree after validation: clean and synchronized with `origin/integration/rc1.1`.

### Application and data validation

- Template rendering: **PASS**.
- Existing dashboard and API routes: **PASS**.
- `/`, `/activity`, `/life-list`, `/device`, `/health`, `/api/metrics`, and `/api/dashboard`: HTTP 200.
- Known-species page: HTTP 200.
- Audio playback: HTTP 200.
- Audio byte-range seeking: HTTP 206.
- SQLite integrity: **PASS** — `ok` through the health validation.
- BirdNET startup and processing: **PASS**.
- Recorder startup and recording: **PASS**.
- Health endpoint: **PASS**, no warnings and no failed recordings.
- Metrics endpoint: **PASS**.

## Raspberry Pi Validation

The candidate was installed with the normal transactional deployer on `project-field-mouse-001`. The deployer retained the preceding release and created a pre-deployment backup for rollback.

- Recorder, BirdNET, and dashboard services: active and enabled.
- Cleanup timer: active and enabled.
- Failed systemd units: none in the validated application set.
- Recorder, BirdNET, and dashboard restart counts: zero after activation.
- Unexpected error-level journal entries after activation: none.
- Queue depth: 0.
- Database integrity: `ok`.
- Failed recordings: 0.
- Observation counts advanced from 5,336 recordings / 1,393 detections immediately after activation to 5,341 recordings / 1,394 detections in the final snapshot.
- New recordings completed and were processed normally; recordings without qualifying detections completed cleanly.
- Health remained HTTP 200 throughout observation.

The expected service stop during the transactional cutover interrupted one in-progress recording and was followed by a clean service start. It did not recur and was not a crash loop.

### Performance observations

- Overview response: approximately 31.9 ms.
- Activity response: approximately 14.7 ms.
- Metrics response: approximately 10.2 ms.
- BirdNET average processing time: approximately 3.78 seconds.
- BirdNET resident memory: approximately 252 MiB during the sampled interval.
- Dashboard master and worker resident memory: approximately 63 MiB combined.
- System memory utilization: approximately 50–52%.
- CPU utilization remained acceptable; BirdNET was approximately 2.1% in the sampled snapshot.
- Temperature: 55.6 C in the final snapshot.
- Root filesystem: 74% used, approximately 15 GiB free; no health warning was raised.

The Verification V2 Raspberry Pi benchmark included in the branch reports 1,000 iterations with a 2.213 ms mean, 2.231 ms p95, 8.774 ms maximum, and no service restarts.

## User Experience Review

- The deployed Activity page presents persisted verification status and combined confidence rather than labelling verified observations as BirdNET-only.
- Observations without verification data retain an explicit, honest BirdNET-only presentation.
- Desktop and 500-pixel responsive captures were coherent, unclipped, and retained usable navigation and verification explanations.
- Dashboard navigation, wildlife-first hierarchy, species pages, Life List, Device page, audio playback, and seeking functioned correctly.
- Existing API contracts were preserved; verification presentation was added only to template-facing row data.

## Remaining Follow-up

- **Non-blocking:** Verification calibration still requires reviewed field observations. The integration uses no unvalidated calibration data, as required.
- **Low:** Perform a physical 360/390-pixel mobile-device review during RC1.1 candidate testing. The installed headless Chromium enforces a 500-pixel minimum layout viewport, so narrower screenshot output is not reliable evidence of the physical layout.
- **Low:** Continue normal unattended observation before public release-candidate approval.
- **Low:** Monitor storage growth. The current 74% usage is healthy and has about 15 GiB free, but retained candidate and rollback artifacts contribute to utilization.

## Recommendation

**READY WITH MINOR FOLLOW-UP**

Dashboard V2 and Verification V2 coexist successfully, automated validation is green, production data is presented accurately, and Raspberry Pi services remain healthy without unexpected restarts. The remaining items are field calibration, a physical narrow-device check, and continued soak observation; none is an integration blocker or a reason to enable unvalidated behavior.
