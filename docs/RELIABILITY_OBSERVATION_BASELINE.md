# Reliability Observation Baseline Report

Observation start: 2026-08-16 22:57 PDT

Branch: `feature/reliability-investigation`

Deployed commit: `6e58c5da642f0b90a0cd3a8e95cbf5ef3cae8a74`

## Deployment

Reliability observation is active in production at:

```text
/opt/project-field-mouse/releases/reliability-observation-2-6e58c5d
```

The transactional deployment completed in 7 minutes 58 seconds after a verified
predeployment backup. Its rollback target is the first reliability release,
`reliability-observation-e43b2dd`; that release in turn retained the RC1.1
integration candidate as its prior target. Recorder downtime during the corrective
switch was approximately eight seconds. Dashboard and BirdNET transitions were
shorter. All long-running services returned active with zero restarts.

The first activation exposed three instrumentation defects without affecting the
application: Windows archive CRLF endings in deployment configuration, an
operator-inaccessible telemetry parent directory, and false cutover-time anomalies
caused by the timer firing while services restarted and observing its own read-only
mount namespace. The bootstrap rejected the invalid sudoers file before replacement.
The final release enforces LF artifacts, lets systemd provision a dedicated
`root:pfm-operators` directory, delays timer collection after activation, and reads
PID 1's host mount namespace. A stable sample then reported no anomalies.

Rollback evidence:

- current: `reliability-observation-2-6e58c5d`;
- previous: `reliability-observation-e43b2dd`;
- verified backup:
  `/var/lib/fieldmouse/backups/predeploy-reliability-observation-2-6e58c5d.zip`;
- automatic rollback remained enabled throughout both deployments.

## Initial baseline

The first stable sample was recorded at 2026-08-16 22:57:20 PDT.

| Metric | Baseline |
| --- | ---: |
| CPU | 0.0% at the sample; 5.6% at immediate health validation |
| Load average | 3.66 / 3.57 / 2.43 after dependency installation |
| Available memory | 666,697,728 bytes (about 636 MiB) |
| Memory used | 35.8% |
| Swap | 187,990,016 bytes (18.1% of zram) |
| Root storage | 76.9% used; 13,437,812,736 bytes free |
| CPU temperature | 53.8 C |
| Firmware throttle/power flags | `0x0` |
| Network errors/drops | 0 / 0 |
| ext4 error count | 0 |
| Root filesystem | ext4, read-write |
| SQLite database | 23,769,088 bytes; integrity `ok` |
| Database queue depth | 1 at follow-up; 0 immediately after first deployment |
| Database recordings | 16,201 at follow-up |
| Database detections | 3,310 |
| Retained WAV files | 1,833 files; 10,463,817,604 bytes |
| Application logs | 202,660,917 bytes |

Service process-tree baselines:

| Service | RSS | Swap | Descriptors | Threads | Restarts |
| --- | ---: | ---: | ---: | ---: | ---: |
| Recorder | 42,401,792 B | 0 | 11 | 3 | 0 |
| BirdNET | 46,252,032 B | 0 | 3 | 4 | 0 |
| Gunicorn | 63,700,992 B | 0 | 17 | 3 | 0 |

Recorder, BirdNET, Gunicorn, backup timer, cleanup timer, and reliability timer were
enabled and active. `/health`, `/api/metrics`, `/api/dashboard`, the home, Activity,
Life List, and Device pages returned HTTP 200. A 1 KiB range request against an
API-confirmed WAV returned HTTP 206 and `audio/wav`. Static CSS returned HTTP 200.
The health response reported the microphone and SQLite healthy with no warnings.

## Telemetry and diagnostics verification

- `fieldmouse-reliability.timer` is enabled and schedules five-minute collection.
- Metrics and `latest.json` are `0640 root:pfm-operators` under
  `/var/log/project-field-mouse-reliability`, with a `0750` parent.
- The operator can read the sample and run the trend summary without elevated file
  access.
- The sample includes CPU, memory, swap, load, root usage, disk I/O, network I/O,
  temperature, firmware flags, service process trees and restarts, SQLite/WAL size,
  recording growth, log growth, timer results, and ext4 health.
- The trend summarizer parsed the production JSONL and reported one boot, one clean
  sample, zero inactive services, zero network errors, zero ext4 errors, and zero
  diagnostic snapshots in the corrected directory.
- Automatic snapshot generation executed under the first release when objective
  conditions were observed. Those conditions were activation artifacts, which the
  corrected release removed; the clean baseline correctly generated no snapshot.
- Automated validation proves daily append behavior, atomic latest-state writes,
  anomaly detection, summary generation, and the 20-snapshot cap. Metrics retain 30
  days and snapshots are capped at 20.
- Global journald remains volatile by explicit design. Equivalent bounded evidence
  preservation is provided by persistent JSONL plus triggered snapshots containing
  kernel warnings, top processes, and recent service journals. A bounded persistent
  global journal remains a separately reviewed future option.

## Observation plan

The station will operate normally for at least seven uninterrupted days or until a
genuine degradation event. At five-minute cadence, seven days yields approximately
2,016 samples.

Automatic diagnostic thresholds are:

- available memory below 128 MiB;
- swap at or above 75%, or growth of at least 128 MiB in one interval;
- five-minute load at or above 6 on this four-core Pi;
- root disk at or above 90%, or at least 1 GiB growth in one interval;
- disk busy at or above 80% across an interval;
- CPU temperature at or above 80 C or any firmware throttle/power flag;
- ext4 errors or a read-only root filesystem;
- any monitored service inactive, restarted, or growing by at least 128 MiB RSS or
  128 descriptors in one interval;
- at least 1,024 descriptors for a service tree;
- any network error/drop counter increase;
- backup or cleanup failure.

A genuine degradation event is any observed loss of SSH/dashboard reachability,
local console hang, sustained operator-visible slowdown, health endpoint failure,
unexpected service restart/inactivity, or objective threshold crossing unrelated to
a planned deployment. Before power cycling, record the exact time and, when safe,
check dashboard/SSH, local console, link LEDs, and power indicators. Preserve the
telemetry directory after recovery.

The observation period concludes after either:

1. at least seven uninterrupted days with expected sample continuity and no genuine
   degradation; or
2. a genuine event with sufficient pre-event metrics and a diagnostic snapshot to
   support root-cause analysis.

No performance tuning, watchdog recovery, service limits, or speculative restart
policy changes are authorized during this observation period.

## Status

**RELIABILITY OBSERVATION ACTIVE.**

The first baseline is captured, continuous collection is scheduled, rollback is
available, and production application behavior remains unchanged.
