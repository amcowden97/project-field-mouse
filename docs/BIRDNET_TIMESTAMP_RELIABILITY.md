# BirdNET timestamp reliability fix

Date: 4 August 2026

Branch: `fix/birdnet-timestamp-processing`

## Root cause

BirdNET predictions are serialized to CSV and read with `csv.DictReader`, so
`start_time` and `end_time` arrive as strings. Current BirdNET output uses
elapsed clock values such as `00:00:12.00`; older/programmatic paths may use
numeric seconds.

`save_detections()` treated both representations as numeric seconds and called
`float()` directly while matching reviewed detections and building the
verification context. `float("00:00:12.00")` raises `ValueError`.

SQLite's REAL affinity could coerce numeric-looking values during insertion,
which obscured the inconsistent boundary handling. The worker rolled back the
transaction, marked the recording `failed`, re-raised the exception, and exited.
Service recovery restarted the worker, but normal selection considers only
`pending` recordings, leaving that recording unprocessed.

## Fix

`app.detectors.timestamps.parse_birdnet_timestamp()` is now the single input
boundary. It converts these supported forms to non-negative seconds:

- integer or floating-point seconds;
- numeric strings;
- `MM:SS` with optional fractional seconds;
- `HH:MM:SS` with optional fractional seconds;
- `datetime.time` and `datetime.timedelta` values.

It rejects empty, negative, non-finite, malformed, and out-of-range clock
components. The pipeline parses each start/end pair once, rejects an end before
its start, and uses the normalized floats for reviewed-detection matching,
SQLite insertion, and verification.

## Retry behavior

RC1 should not automatically retry every failure without an attempt budget and
error classification. Deterministic model/runtime failures could otherwise
create a hot retry loop and starve healthy recordings.

The supported RC1 recovery is explicit administrative retry:

```shell
python -m app.detectors.process_recording \
  --database data/database/fieldmouse.db \
  --recording-id RECORDING_ID
```

Explicit ID selection accepts a `failed` recording. A successful run commits
the detections and changes its status to `processed`. Existing unreviewed
BirdNET detections for that recording are replaced transactionally, preventing
duplicates; reviewed detections remain protected.

The future retry design should add attempt count, next-attempt time, and
retryable/permanent error classification in an additive migration. That is not
necessary for this focused RC1 defect.

## Regression validation

`tests/test_birdnet_timestamps.py` covers:

- `00:00:12.00` and other clock/numeric forms;
- invalid and non-finite values;
- valid timestamp range insertion as REAL seconds;
- continuous-worker processing without an exception/restart;
- retrying a previously failed ID;
- repeated retry without duplicate detections;
- rollback of partial inserts on a malformed prediction;
- successful administrative recovery after rollback.

Local focused result:

```text
22 passed (BirdNET import stub; inference mocked, worker/database path real)
ruff: All checks passed
```

Without the optional BirdNET runtime or import stub, the same suite reports 19
passed and skips the three pipeline integration cases.

The full portable-Windows suite also ran. Eight unrelated configuration tests
failed because that lightweight interpreter lacks the `tzdata` package; the
remaining tests passed. The pinned production environment carries the complete
runtime closure and should run the full suite during release validation.

## RC1 recommendation

The confirmed timestamp-processing code blocker is resolved. Before removing
the operational release gate, deploy through the normal RC1 validation process
and reprocess one affected real recording by ID. Confirm it becomes `processed`,
its timestamps are numeric seconds, detections are present exactly once, and the
BirdNET service does not restart.
