# RC1.1 Verification V2 development report

Date: 5 August 2026

Branch: `feature/verification-v2`

## Outcome

RC1.1 builds on the Foundation Phase verification package rather than replacing
it. BirdNET remains the primary classifier and its raw confidence remains on the
`detections` row. Verification independently combines enabled evidence sources
and stores a separate consensus score, status, rationale, evidence ledger, and
review priority.

## Architectural decisions

- Immutable `DetectionContext` objects isolate evidence modules from storage.
- `VerificationPlugin` is the stable extension contract. Modules return a
  verdict, evidence strength, configured weight, explanation, and structured
  details without mutating detections.
- Weighted log-odds combines evidence because independent support compounds and
  opposition can cancel support. It also exposes an exact signed contribution
  per source. Defaults are hypotheses pending local calibration, not scientific
  constants.
- BirdNET is always shown separately as the prior. Even detections above the
  strong-prior threshold run independent modules; BirdNET cannot corroborate
  itself.
- Missing modules become explicit, zero-weight evidence rather than silently
  reducing a score.
- Verification uses nested SQLite savepoints. Failures preserve the BirdNET
  insert and, when persistence remains available, create an uncertain,
  high-priority `verification_unavailable` record for later review.
- Existing verification tables and JSON fields are sufficient, so RC1.1 needs
  no storage migration for these improvements.

## Initial evidence modules

The included modules cover geographic occurrence, season and time of day,
verified station history, recording quality, and an optional process-isolated
second classifier. Geographic and seasonal profiles are local versioned files;
the real-time path has no cloud dependency. Station history only trusts earlier
verified/probable observations, preventing repeated raw false positives from
becoming self-reinforcing evidence.

## Trade-offs

- A rule still rejects BirdNET detections below the configured floor without
  running expensive modules. This preserves current filtering behavior and Pi
  capacity, but means below-floor candidates do not receive a full assessment.
- Log-odds assumes evidence sources are sufficiently independent. Geography,
  season, and station history can correlate, so their weights must be calibrated
  conservatively on reviewed local recordings.
- Generic audio heuristics identify quality risks, not the species producing a
  sound. They appropriately influence trust but cannot verify taxonomy alone.
- Catching verification failures favors uninterrupted detection capture. Errors
  remain visible through logs, structured unavailable evidence, and review
  priority rather than stopping the worker.

## Extension points

Future modules can implement the existing plugin contract for weather, eBird
frequency snapshots, camera evidence, nearby stations, consecutive detections,
or additional classifiers. External services should remain adapters with
timeouts and explicit unavailable results. Dashboard consumers can render the
current evidence ledger without backend schema changes.

## Later RC1.1 work

- Calibrate weights and thresholds against held-out, locally reviewed clips.
- Benchmark the enabled profile on Raspberry Pi 5 under recorder load.
- Add a consecutive-detection module with recording-boundary and duplicate
  safeguards.
- Version evidence-module implementations and configuration in persisted output.
- Add an administrative job to retry `verification_unavailable` records without
  rerunning BirdNET.
- Expand the curated Washington occurrence profile with reviewed provenance.

Weather services, camera support, dashboard changes, and live external-data
providers remain intentionally outside this milestone.

## Validation

The focused verification, BirdNET-processing regression, and migration suites
pass 42 tests. These exercise individual evidence modules, missing and
contradictory evidence, rare and common-context behavior, exact consensus
contributions, high-confidence independent review, persistence, reviewed-history
preservation, and both verification-execution and verification-persistence
failure isolation.

The portable Windows interpreter used for this work does not include the
optional BirdNET runtime, so pipeline tests use an import-only stub while
inference is mocked. The same interpreter also lacks `tzdata`; the otherwise
compatible repository suite reaches eight pre-existing configuration failures
and one collection error for that dependency. Production/CI validation should
run the complete suite from the pinned dependency set.
