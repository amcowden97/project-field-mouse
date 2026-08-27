# v1.1.0 Release Acceptance Report

Date accepted: 2026-08-26 PDT

Runtime candidate: `fb9b131548c1dd4e2691c98490a7ddfc58860573`

Target version: `v1.1.0`
Status: **ACCEPTED FOR PUBLICATION**

## Executive summary

RC1.1 completed transactional deployment, controlled reboot recovery, and
approximately seven days of normal production operation. Recorder, BirdNET, and
dashboard services remained active with no relevant restarts after the controlled
reboot. Normal recordings continued through BirdNET processing into SQLite, the queue
remained at zero, dashboard playback and seeking passed, and SQLite integrity remained
`ok`.

A storage warning discovered during final closure was traced primarily to historical
audio retained in the legacy source checkout. HQ approved a controlled cleanup only
after the 100 RC1.2 research-candidate recordings were verified by SHA-256. The cleanup
reclaimed approximately 13.98 GB, preserved database and detection history, and restored
root storage from approximately 90% used to 66% used with approximately 19.81 GB free.
The health endpoint subsequently returned HTTP 200.

## Deployment and reliability evidence

- Active runtime release: `/opt/project-field-mouse/releases/rc1.1.1-fb9b131`.
- Previous rollback release: `/opt/project-field-mouse/releases/rc1.1.1-4e74b15`.
- Database migrations: versions 1 through 5, unchanged by release administration.
- Controlled reboot: passed; recorder, BirdNET, dashboard, cleanup timer, and
  reliability timer recovered automatically.
- Representative post-reboot recording: `44218`, processed successfully by BirdNET.
- Production counts at publication preflight: 29,025 recordings and 4,901 detections.
- Failed recordings: 0; queue depth: 0.
- Core-service restarts: 0 at publication preflight.
- `/health`: HTTP 200, status `ok`.
- SQLite integrity: `ok`.
- Root storage: 66% used with approximately 19 GB free.
- `/tmp`: approximately 2% used.

## Historical audio cleanup

The HQ-approved cleanup intentionally expired selected historical source audio while
preserving the corresponding SQLite recording rows, detection records, and scientific
history. The 100 recordings referenced by the RC1.2 candidate research pool were
verified by SHA-256 before cleanup. This package remains preliminary candidate material,
not Ground Truth Dataset v0.1.

The cleanup resolved the immediate release blocker but is not a long-term retention
solution. Detection-bearing audio has previously accumulated at approximately 1.2
GB/day net. Post-cleanup headroom was estimated at approximately 11 days before the
configured warning threshold. Curated species recording retention remains planned
post-v1.1.0 work.

## Validation

- Automated tests: 91 passed.
- Ruff: zero findings.
- Compile validation: passed.
- Candidate CI run `32224121200`: passed.
- Release-package CI run `32226974927`: passed.
- Overview, Activity, Life List, Species, Device, metrics, and dashboard API: passed.
- Audio playback: HTTP 200.
- Audio byte-range seeking: HTTP 206.
- Recording and BirdNET pipelines: passed.
- Cleanup and database-history preservation: passed.
- Release retention and rollback availability: passed.

## Known non-blocking limitations

- Detection-bearing audio can accumulate faster than the current retention system can
  sustainably remove it; operators must monitor forecasts and storage warnings.
- Verification weights remain conservative pending independently reviewed field data.
- Rare-species cleanup fails closed without an authoritative rare-species list.
- Off-device webhook notification is optional and disabled by default.
- Weather content remains a non-live placeholder.
- The dashboard is intended for a trusted local network unless protected by an
  operator-managed authenticated reverse proxy.

## Decision

HQ accepts the production evidence, controlled storage cleanup, preserved scientific
history, rollback posture, and documented retention limitation. No P0 or P1 release
defect remains. Project Field Mouse v1.1.0 is approved for publication.
