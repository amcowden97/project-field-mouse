# Production Recording Outage — 2026-08-18

## Status

**Recovered and verified at 2026-08-18 21:47 PDT.** No reboot occurred. No
database rows or irreplaceable recordings were deleted. The current retention
policy expired 1,235 eligible audio files while preserving their database rows.

**Release assessment: RC1.1 promotion is on hold.** The deployed candidate can
remain online under close disk monitoring, but RC1.1 should not be promoted until
the critical prevention items below are implemented and production-tested.

## Impact

- Recording was unavailable from 2026-08-18 02:48 PDT until recovery at
  2026-08-18 21:46 PDT: approximately 18 hours 58 minutes.
- The recorder systemd unit remained active, but every capture failed with ENOSPC.
- BirdNET remained active and completed the final queued recording. It had no new
  recordings to process during the outage.
- The dashboard remained available but showed stale recording data.
- Scheduled backup and cleanup jobs failed after the disk reached capacity.

## Incident timeline

| Time (PDT) | Event |
|---|---|
| Aug 16 22:10 | Reliability baseline measured root at 84% used with about 9.1 GiB available. |
| Aug 17 22:47 | Last successful pre-incident cleanup expired 45 eligible recordings and reclaimed 247.2 MB. |
| Aug 18 02:47:26 | Last successful pre-outage recording completed, database ID 33357. |
| Aug 18 02:47:29–02:47:33 | BirdNET processed recording 33357 successfully with zero detections. |
| Aug 18 02:48:24 | First recorder failure: `No space left on device` while writing the 02:47:27 WAV. |
| Aug 18 03:22 | Scheduled backup failed with `[Errno 28] No space left on device`. |
| Aug 18 04:52 | Scheduled cleanup failed with `sqlite3.OperationalError: database or disk is full`. |
| Aug 18 10:54 | Cleanup failed again with the same error. |
| Aug 18 16:54 | Cleanup failed a third time with the same error. |
| Aug 18 19:54 onward | Reliability monitor emitted repeated disk/maintenance diagnostic snapshots. |
| Aug 18 21:40 | Incident response confirmed root filesystem at 100%, zero available bytes, healthy inodes, and repeated recorder ENOSPC errors. |
| Aug 18 21:43 | Recorder stopped to end repeated failed capture attempts. No reboot performed. |
| Aug 18 21:44 | Verified inactive legacy `.venv` was not referenced by any process; removed it and restored 2.0 GiB working space. |
| Aug 18 21:45 | Existing cleanup service ran with unchanged policy; 1,235 files expired, 1,235 DB rows preserved, 6.6 GiB reclaimed. Root fell to 85% used. |
| Aug 18 21:45 | Recorder started. |
| Aug 18 21:46:20 | Recording 33358 completed successfully at 5,760,044 bytes. |
| Aug 18 21:46:23–21:46:28 | BirdNET processed recording 33358 successfully. |
| Aug 18 21:47:21 | Recording 33359 completed successfully at 5,760,044 bytes. |
| Aug 18 21:47:28–21:47:33 | BirdNET processed recording 33359; queue returned to zero. |
| Aug 18 21:47:41 | Dashboard reported recorder fresh; `/health` returned `ok`, SQLite integrity `ok`, all services active, no warnings, and about 9.25 GB free. |

## Root cause analysis

### Confirmed immediate cause

Recording stopped because the root filesystem exhausted its available data blocks.

Evidence:

- `df -h` reported `/dev/mmcblk0p2` at 100% with zero available.
- Inodes were only 13% used, excluding inode exhaustion.
- Recorder journal reported `No space left on device` on every attempted WAV.
- The first ENOSPC event immediately followed the final successful recording.
- Once free space was restored, the unchanged recorder and microphone produced
  complete WAVs and BirdNET processed them normally.

### Confirmed contributing causes

1. **Recording production exceeded remaining capacity between cleanup windows.**
   The deployed adaptive schedule records a 5,760,044-byte WAV every 60 seconds,
   a theoretical 7.7 GiB/day. Telemetry showed current production recordings grow
   from 10.46 GB/1,833 files to 19.60 GB/3,481 files during the observed period.

2. **The station began with insufficient storage headroom.** The reliability
   baseline was already 84% used. Large existing consumers were:

   - about 19.6 GB of current production audio at failure time;
   - 14 GB in seven deployment releases, although only `current` and `previous`
     were referenced;
   - 12 GB of preserved legacy recordings under
     `/home/amcowden97/Project-Field-Mouse/data`;
   - about 245 MB of application logs.

3. **Release retention is absent.** `pfm-deploy` creates a new approximately 2 GB
   environment but does not prune unreferenced releases after a successful deploy.
   Five unreferenced large releases consumed about 10 GB beyond the active and
   rollback releases.

4. **Cleanup cannot self-recover at zero free space.** Candidate discovery performs
   a grouped SQLite query. With no SQLite temporary working space, cleanup failed
   before it could delete eligible files. The six-hour timer retried but had no
   emergency low-space path.

5. **Detection-bearing retention can grow indefinitely with the deployed config.**
   The cleanup intentionally fails closed when no authoritative rare-species list
   is configured, preserving every detection-bearing recording. This protected
   data during the incident but needs explicit capacity planning.

6. **Telemetry detected but did not alert or recover.** It accurately captured disk
   growth from 76.9% to 100%, cleanup/backup failures, and repeated diagnostic
   snapshots. There is no external notification channel or automated emergency
   cleanup, so detection did not result in intervention before outage.

### Excluded by evidence

- **Recorder crash:** excluded. Unit remained active with zero restarts; child
  captures failed specifically on ENOSPC.
- **USB microphone failure:** excluded. Health reported `plughw:2,0` healthy and it
  recorded successfully immediately after space recovery.
- **Filesystem corruption/read-only remount:** excluded. Root remained read-write,
  ext4 error count was zero, and SQLite integrity was `ok`.
- **Thermal or power throttling:** excluded as trigger. Maximum observed temperature
  was 58.2 C, firmware throttle flags remained zero.
- **BirdNET failure:** excluded. It processed the last pre-outage and first two
  post-recovery recordings; restart count remained zero.
- **Inode exhaustion:** excluded at 13% inode use.

## Evidence summary

- Root filesystem: 57 GiB, 100% used, zero available at discovery.
- Database: integrity `ok`, about 26.2 MB plus a 4.2 MB WAL.
- Last pre-outage recording: ID 33357, recorded 02:46:26 PDT.
- Last pre-outage BirdNET completion: 02:47:33 PDT.
- Latest detection at discovery: White-breasted Nuthatch, recording time
  Aug 17 23:13:51 PDT, detection row created Aug 18 06:15:04 UTC.
- Queue at discovery: zero; BirdNET had processed everything successfully written.
- Reliability samples: 516 from one boot, Aug 16 22:57 through Aug 18 21:38 PDT.
- Services: active, zero restarts; ext4 errors zero; root never read-only.
- Persistent evidence archive:
  `evidence/pfm-incident-20260818.tar.gz` (271,577 bytes), containing complete
  reliability JSONL/snapshots and relevant service journals.

### Telemetry assessment

The reliability work succeeded at evidence capture. It preserved:

- the complete 76.9% → 100% disk trend;
- current recording bytes/count growth;
- cleanup and backup failure status;
- service RSS, swap, descriptors, threads, CPU, and restart counts;
- root mount state, ext4 errors, temperature, and throttle flags;
- repeated diagnostic snapshots with service journals.

Gaps exposed by the incident:

- thresholding starts at 90%, without graduated 80/90/95 severity;
- no off-device/page notification exists;
- no forecast such as hours-to-full is calculated;
- backup-directory size and deployment-release size are not inventoried;
- “service active” did not represent recorder functional success;
- the health endpoint warned on disk but did not explicitly elevate stale recording
  age into its warnings list;
- diagnostic snapshots are capped at 20, so early threshold-crossing snapshots can
  be displaced by repeated identical 100% snapshots.

## Recovery actions

1. Preserved statuses, journals, filesystem/inode use, APIs, telemetry, diagnostics,
   storage inventory, active release links, and last processing timestamps.
2. Copied a complete evidence archive off-device before final reporting.
3. Stopped the recorder to prevent repeated failed writes.
4. Removed only the verified inactive, rebuildable legacy virtual environment at
   `/home/amcowden97/Project-Field-Mouse/.venv`, restoring 2.0 GiB. No source,
   legacy recording, database, or active/rollback environment was removed.
5. Ran the existing production cleanup service without modifying retention policy.
6. Cleanup expired 1,235 policy-eligible audio files, reclaimed 6.6 GiB, and
   preserved all 1,235 database rows as `audio_expired`.
7. Restarted the recorder and verified two complete recordings.
8. Verified BirdNET processed both, queue depth returned to zero, dashboard
   freshness updated, SQLite integrity remained `ok`, and `/health` returned `ok`.

No reboot was performed. The 12 GB legacy recording corpus and detection-bearing
production audio were not deleted. Temporary evidence staging files were removed
only after the archive was copied successfully.

## Preventive recommendations

Emergency recovery changes are complete. The following are separate product and
operations work; none were applied during the incident.

### Critical before RC1.1 promotion

1. **Add graduated disk alerts:** warning at 80%, high at 90%, critical at 95%, and
   emergency at both 97% and an absolute free-space floor. Alert on free bytes as
   well as percentage because ext4 reserved blocks made APIs show different values.
2. **Add an emergency cleanup path that works under ENOSPC.** Candidate selection
   must not require a large SQLite temporary sort. Precompute/index eligibility,
   process bounded batches, reserve a small root-only recovery file, or combine
   these approaches. Test at zero reported available bytes.
3. **Implement deployment-release pruning.** After successful activation retain
   `current`, `previous`, and at most one explicitly pinned diagnostic release.
   Never delete a symlink target. Report expected and reclaimed bytes.
4. **Add external alert delivery.** Send disk thresholds, recorder freshness failure,
   cleanup failure, and backup failure off-device. Local JSON alone cannot summon
   an operator.
5. **Make recorder health functional.** Mark health degraded when the newest
   successful DB recording exceeds the stale threshold even if systemd is active.
   Track consecutive capture failures and last successful capture explicitly.

### High

1. **Forecast storage exhaustion.** From recent recording-byte growth and cleanup
   reclaim rate, expose GiB/day and estimated hours-to-80/90/95/100%. Current
   one-minute PCM cadence can consume about 7.7 GiB/day before cleanup.
2. **Run cleanup more frequently or event-driven at low space.** Keep the normal
   retention timer, but trigger bounded cleanup when free space crosses a threshold.
   Use locking so scheduled and emergency cleanup cannot overlap.
3. **Inventory all major consumers in telemetry:** current recordings, legacy data,
   backups, application logs, pip cache, release environments, and operator home
   staging. Emit `unknown/inaccessible` rather than silently omitting a subtree.
4. **Resolve the detection-retention policy.** Configure and govern an authoritative
   rare-species list or define a bounded preservation tier. Continue to fail closed
   until the policy is approved, but forecast its unbounded component explicitly.
5. **Add recorder backoff on ENOSPC.** Stop one-minute child-process churn after a
   small consecutive-failure threshold while keeping the supervisor observable.

### Medium

1. Add dashboard cards for free GiB, growth/day, time-to-full, last cleanup result,
   bytes reclaimed, last backup result, consecutive recording failures, and last
   successful recording/BirdNET timestamps.
2. Deduplicate diagnostic snapshots while an unchanged anomaly persists, preserving
   the first crossing, escalation points, and latest state.
3. Enable a bounded persistent journal after explicit operational review; the
   current journal is volatile across reboot.
4. Move preserved legacy recordings off the root filesystem to verified external
   storage. Do not delete them as an emergency shortcut.
5. Add a production fault-injection test that fills a disposable filesystem,
   verifies warning escalation and emergency cleanup, and proves recorder recovery
   without reboot or database-history loss.

## RC1.1 release decision

**Change status to HOLD / P0 storage reliability blocker.** The recorder and all
downstream detection stopped for nearly 19 hours while systemd still reported the
service active. The incident is recovered, but the same failure can recur because
release pruning, external alerting, functional recorder health, and ENOSPC-safe
cleanup are not yet implemented.

Exit criteria to restore release status:

1. critical prevention changes implemented and reviewed;
2. ENOSPC fault test passes without data-history loss;
3. release pruning demonstrated with `current` and `previous` protected;
4. threshold notifications verified off-device;
5. at least 24 hours of one-minute production recording shows stable free-space
   floor, successful cleanup/backup cycles, fresh dashboard state, and zero recorder
   failures.
