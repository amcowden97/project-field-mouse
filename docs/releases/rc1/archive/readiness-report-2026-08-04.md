# RC1 Readiness Report — 2026-08-04

## Recommendation

**Additional work required.**

Do not merge `integration/v3` into `master` or tag `v3.0.0-rc1` yet. The
BirdNET timestamp parsing defect is a release blocker because affected
recordings are marked failed and are not retried, permanently losing their
detection results even though the WAV files remain intact.

## Merge summary

The integration branch contains the completed work from:

- Bird Verification / AI (`feature/bird-verification`);
- Dashboard V3 (`feature/dashboard-v3-complete`);
- RC1 runtime compatibility (`feature/runtime-compatibility-rc1`);
- RC1 failed-release and cache retention (`feature/storage-retention-rc1`);
- history-preserving storage stabilization (`feature/infrastructure`).

Infrastructure was merged at `3064444`. Its only conflict was in
`app/services/storage_cleanup.py`, where the earlier centralized database-path
configuration overlapped the new retention implementation. The resolution
preserved both the centralized path and the newer behavior that expires audio
without deleting database history, protects configured rare species, and
fails closed when no authoritative rare-species list exists.

No feature work, unrelated refactor, master merge, or release tag was
performed.

## Regression results

The clean `3064444` archive was copied to the Raspberry Pi and its SHA-256 was
verified as:

```text
1892738dce27cdea1484e6b59b86177527f662941c9cbc9741594fc3d2662b7d
```

| Check | Result | Evidence |
| --- | --- | --- |
| Pytest | PASS | 43 passed in 0.77 seconds |
| Ruff | PASS | No findings |
| Compileall | PASS | No compilation errors |
| Local `git diff --check` | PASS | No candidate whitespace errors |
| Startup preflight | PASS | App/config imports and BirdNET 0.2.16 prediction strategy resolved |
| Focused merged cleanup tests | PASS | 3 passed |

The active legacy checkout's `git diff --check` is not clean because the
validated Infrastructure deployment is present there as uncommitted changes.
This is deployment-state evidence, not a defect in the clean candidate
archive.

## Raspberry Pi validation

Validation host: `project-field-mouse-001`, booted 2026-08-04 11:56:32 PDT.

| Subsystem | Result | Evidence |
| --- | --- | --- |
| Recorder | PASS | Enabled, active, no restarts, new 5,760,044-byte WAVs and rows created |
| BirdNET worker | FAIL | Enabled and currently active, but 12 automatic restarts since boot and failed rows are not retried |
| Dashboard overview | PASS | HTTP 200, 32 ms sample response |
| Activity | PASS | HTTP 200, 13 ms |
| Life List | PASS | HTTP 200, 22 ms |
| Species page | PASS | Black-capped Chickadee returned HTTP 200, 49 ms |
| Device page | PASS | HTTP 200, 39 ms |
| Static assets | PASS | Sample CSS and hero image returned HTTP 200 |
| Audio playback | PASS | HTTP 200 full response; byte-range request returned HTTP 206 and 1,024 bytes |
| Metrics | PASS | `/api/metrics` returned HTTP 200 |
| Health | PASS | HTTP 200, status `ok`, no warnings |
| SQLite | PASS | Integrity `ok`; 2,748 recordings and 1,034 detections at capture |
| Cleanup | PASS | Timer enabled/active; last safe apply exited 0; history-preserving behavior tested and audited |
| Storage | PASS (short term) | 57 GiB total, 45 GiB used, 9.9 GiB free (82%) |
| Boot recovery | PASS | Recorder, BirdNET, dashboard, and cleanup timer enabled and active after current boot |

The database status distribution at capture was:

```text
audio_expired  738
failed         148
processed      1862
```

The health process cannot inspect systemd as its service user and reports
service and microphone state as `unknown`; it nevertheless returned HTTP 200
because database, disk, temperature, network, and recording freshness checks
were healthy. This is an observability limitation, not the primary RC1
blocker.

## BirdNET timestamp investigation

### Root cause

BirdNET emits timestamp strings such as `00:00:12.00`, `00:00:36.00`, and
`00:00:39.00`. `save_detections()` passes these values directly to `float()`,
which raises:

```text
ValueError: could not convert string to float: '00:00:12.00'
```

The worker catches the processing exception only to roll back, mark the
recording `failed`, commit a failure metric, and re-raise. Systemd restarts the
service after 15 seconds.

### Reliability impact

- Service recovery: **yes**, systemd restarts the worker.
- Audio loss: **no**. Five sampled failed WAVs still existed at their expected
  paths and were each 5,760,044 bytes.
- Detection loss: **yes**. Affected rows had zero committed detections after
  BirdNET produced non-empty output.
- Retry behavior: **no retry**. The worker selects only `pending` rows, while
  affected rows are permanently marked `failed`.
- Observed frequency: five failures in an approximately eleven-minute sample,
  contributing to 12 worker restarts since boot.

This is a release blocker because automatic process recovery does not recover
the lost processing result.

## Remaining known issues

### Blocker — BirdNET timestamp parsing and failed-row recovery

The owning team must confirm the accepted timestamp formats, implement and
test deterministic conversion, and define safe retry/recovery for the existing
failed rows. Validation must prove detections commit without duplicate rows and
the worker does not enter a restart loop.

### High — No authoritative rare-species list

Cleanup correctly fails closed and retains all detection-bearing audio when
rarity cannot be determined. This protects data and is safe for RC1 testing,
but detection audio can grow without bound. The measured retained set was
approximately 5.94 GB, with historical growth around 0.7–1.1 GB per day.
Wildlife/Release ownership must provide or explicitly approve the station's
rarity authority before long-term unattended operation.

### Medium — Health service visibility

The health response reports the microphone and systemd services as `unknown`
because its runtime identity cannot perform those checks. Direct systemd
validation passed, but the endpoint does not independently prove service
health.

### Medium — Production checkout state

The active checkout contains the storage-stabilization deployment as
uncommitted changes. The clean integration archive passed regression testing,
but it was intentionally not activated after the BirdNET blocker was
confirmed. The next cutover must use the transactional deployer and retain
rollback capability.

## Required next steps

1. Assign timestamp parsing and failed-row recovery to BirdNET ownership.
2. Add regression fixtures for clock-formatted start/end times and failure
   retry behavior.
3. Reprocess a controlled failed WAV and prove detections persist once, with no
   service restart.
4. Resolve or formally accept the rare-species authority limitation and record
   the resulting storage budget.
5. Produce a clean candidate from `integration/v3`, rerun the 43-test suite,
   and deploy it with the transactional deployer.
6. Repeat end-to-end recording, detection, dashboard, cleanup, health, and
   reboot validation before reconsidering RC1 approval.
