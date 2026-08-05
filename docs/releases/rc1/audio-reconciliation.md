# RC1 storage and audio reconciliation

Validation date: 2026-08-04 PDT

## Outcome

The storage cleanup reclaimed 4.25 GB while preserving SQLite recording and
detection history. Production disk utilization fell from 89% to 82%, and the
health endpoint recovered from HTTP 503 to HTTP 200.

The preserved post-cleanup report is
[`evidence/audio-audit-report-post-cleanup-20260804.json`](evidence/audio-audit-report-post-cleanup-20260804.json).
The station copy is retained at:

`/home/amcowden97/pfm-audio-audit/audio-audit-report-post-cleanup-20260804.json`

## Current inventory

| Measure | Result |
| --- | ---: |
| Filesystem use | 82% |
| Free space | 10.69 GB (about 10 GiB in `df -h`) |
| WAV files at final audit snapshot | 2,020 |
| SQLite recording rows at final validation | 2,729 |
| SQLite detections | 1,034 |
| Settled referenced WAVs | 1,988 |
| Settled orphan WAVs | 31 |
| Unsettled/in-progress WAVs | 1 |
| SQLite integrity | `ok` |

Counts change continuously because the recorder is active. The audit excludes
unreferenced files newer than five minutes so an in-progress recording is not
misclassified before its database transaction commits.

## Orphan classification

| Category | Count | Size | Action |
| --- | ---: | ---: | --- |
| Duplicate recordings | 0 | 0 B | None |
| Legacy recording | 1 | 1.4 MiB | Preserve |
| Missing database rows | 0 | 0 B | None |
| Historical ingestion failures | 30 | 113.2 MiB | Preserve for recovery decision |
| Unknown | 0 | 0 B | None |

The earlier approximation of roughly 1,000 orphans was a reconciliation error:
project-relative database paths (`data/recordings/...`) were compared directly
with absolute filesystem paths. After resolving both forms from the project
root, those files were confirmed referenced.

Two additional unreferenced WAVs were zero bytes, had no SQLite references, and
shared the SHA-256 of an empty file. They contained no recoverable audio and
were deleted individually after verification. No other orphan was deleted.

The 30 historical ingestion failures have valid current-layout filenames but no
database row. Available logs do not retain evidence of the original database
failure, so automatic row reconstruction or deletion is not justified. Their
small size does not materially affect station capacity.

## Retention correction

The previously installed cleanup removed both WAV files and their recording
rows. Its 2026-08-04 12:09 run removed 311 zero-detection files and 311 rows.
SQLite remained consistent, but deleting history violates the RC1 requirement.

The corrected cleanup now:

- removes eligible audio only;
- preserves recording rows and detections;
- marks retained recording history as `audio_expired`;
- skips pending, processing, and already-expired rows;
- is safe on repeated execution and missing files;
- preserves any configured rare species forever;
- preserves every detection-bearing recording when the authoritative
  `rare_species` list is absent or empty;
- retains empty recordings for 24 hours;
- uses a three-day retention period for common-species recordings only after
  the rare-species authority is populated.

The verified apply expired 737 zero-detection audio files. A second run crossed
the moving 24-hour cutoff and safely expired one additional file. Database row
and detection counts did not decrease. Seven focused storage tests and the full
36-test production suite passed.

## Production validation

- Recorder: active and committing new 5,760,044-byte WAVs and SQLite rows.
- BirdNET: processed zero-detection recordings after cleanup, but later failed
  when a detection contained `start_time = "00:00:12.00"`. The existing parser
  attempted `float(...)`, exited with status 1, and entered systemd auto-restart.
  This pre-existing runtime-compatibility defect is outside the storage change.
- Dashboard: root, Activity, Life List, actual species page, and metrics return
  HTTP 200.
- Playback: recording 9779 returned HTTP 206 and a valid mono, 48 kHz, 16-bit
  PCM WAV.
- Health: HTTP 200 with no disk warning after cleanup.
- Cleanup timer: active and enabled; next invocation uses the installed safe
  module from the legacy production working directory.
- Rare species: no detection-bearing row has status `audio_expired`; automated
  tests verify explicit rare-species protection and fail-closed empty-list
  behavior.
- Rollback evidence: consistent 4.8 MiB SQLite backup at
  `/home/amcowden97/pfm-audio-audit/fieldmouse-pre-retention-20260804.db`;
  integrity `ok`, 2,723 recording rows, and 1,034 detections at capture time.

## Remaining operational risk

The station does not yet have an authoritative rare-species list. Cleanup
therefore fails closed for all detection-bearing audio. The retained detection
set contains 580 recordings using 5.94 GB; historical growth reached roughly
0.7-1.1 GB per day. The 24-hour empty-audio policy prevents immediate disk
exhaustion, but detection audio can still grow without bound.

RC1 storage is operationally safe in the short term, but long-term unattended
operation remains blocked until the wildlife/release owner supplies the station
rare-species list (or explicitly authorizes an empty list as authoritative).

Overall RC1 validation is also blocked by the existing BirdNET timestamp parser
failure described above. Storage cleanup did not modify BirdNET code or data.
