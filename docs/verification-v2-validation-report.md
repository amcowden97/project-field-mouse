# Verification V2 validation and integration readiness report

Date: 5 August 2026

Branch: `feature/verification-v2`

Recommendation: **ADDITIONAL DEVELOPMENT REQUIRED**

> Superseded for the scientific-calibration milestone by the
> [5 August field validation report](verification-calibration-report.md), whose
> evidence-gated conclusion is **ADDITIONAL FIELD DATA REQUIRED**.

Verification V2 passes complete engineering validation in the pinned local
environment. It is not yet ready for RC1.1 integration because no reviewed
Field Mouse evaluation dataset or production Raspberry Pi benchmark evidence
was available. Those are explicit acceptance requirements and cannot be
replaced by synthetic data or workstation measurements.

## Validation

An isolated environment was created with CPython 3.13.14, matching CI's Python
3.13 line. `requirements-dev.txt` and `requirements-production.txt` resolved to
74 compatible packages.

| Check | Result |
| --- | --- |
| Pinned dependency installation | Passed |
| Dependency compatibility check | 74 packages compatible |
| BirdNET import/version | Passed, 0.2.16 |
| `tzdata` import/version | Passed, 2026.3 |
| `ZoneInfo("UTC")` | Passed |
| `ZoneInfo("America/Los_Angeles")` | Passed |
| Full pytest suite | 71 passed |
| Ruff (`app`, `tests`) | Passed |
| Compileall (`app`) | Passed |

Validation found and corrected three defects:

1. `tzdata` was absent from the production dependency closure. Windows could
   not load configured IANA time zones. `tzdata==2026.3` is now pinned.
2. SQLite's connection context manager commits or rolls back but does not close
   the connection. Backup snapshot handles are now closed explicitly, preventing
   Windows temporary-file lock failures.
3. `psutil.sensors_temperatures` is not available on every platform. Health
   reporting now treats an unavailable sensor API as missing evidence.

No Verification V2 regression remained after these corrections.

## Calibration

No reviewed local evaluation manifest or production station database was
available in the workspace. The databases and WAV files under `data/processed`
are pytest artifacts and are not scientific observations. `samples/detections.json`
contains synthetic species/confidence ranges without ground truth.

Therefore no weight or threshold was changed. The current profile remains
explicitly marked `uncalibrated_defaults`:

| Evidence source | Current weight | Decision |
| --- | ---: | --- |
| BirdNET prior | 1.00 | Retain pending calibration |
| Optional second model | 1.25 | Retain; disabled by default |
| Geographic occurrence | 0.65 | Retain pending local rare/common review |
| Season/time | 0.55 | Retain pending seasonal review |
| Audio quality | 0.50 | Retain pending false-positive analysis |
| Verified station history | 0.45 | Retain pending longitudinal data |

Calibration remains required across common species, rare species, borderline
confidence, reviewed detections, and known false positives. False-negative
measurement additionally requires independently sampled background recordings;
a detection-only export cannot measure calls that BirdNET missed.

Required next evidence:

- a versioned, immutable reviewed manifest;
- station/time-grouped training and held-out partitions;
- class-balanced rare/common and positive/negative examples;
- baseline BirdNET and Verification V2 metrics on the same held-out records;
- source-ablation and reliability/calibration curves;
- written rationale for every promoted weight or threshold change.

## Performance

No production Raspberry Pi endpoint, credentials, database, or approved test
window was configured. Raspberry Pi acceptance is therefore not established.

The existing profiler was exercised for 100 iterations against a generated
simulator detection on the Windows development host. This is a tooling smoke
test only:

| Measurement | Local smoke result |
| --- | ---: |
| Manager startup | 0.681 ms |
| Mean verification latency | 0.945 ms |
| p95 verification latency | 0.938 ms |
| Maximum verification latency | 19.806 ms |
| Process CPU time | 0.09375 s / 100 iterations |
| Mean sampled process CPU | 101.661% |
| Peak process RSS | 37,756,928 bytes |
| Temperature | Unavailable on host |

These figures do not characterize Raspberry Pi CPU, memory, thermal behavior,
BirdNET contention, processing throughput, or station responsiveness. They must
not be used as release thresholds.

The production Pi run must measure Verification V2 disabled versus enabled on
the same workload, including BirdNET inference latency, queue depth, recorder
continuity, CPU, RSS, temperature/throttling, and overall health. Acceptance
requires no recorder dropouts, no growing processing backlog, and adequate
thermal and memory headroom during unattended operation.

## Architecture review

The architecture is maintainable and ready for extension:

- `DetectionContext` is immutable and separates modules from persistence.
- `VerificationPlugin.verify()` is a small stable public contract.
- Modules execute independently and failures become explicit neutral evidence.
- Consensus retains BirdNET confidence separately and records exact signed
  evidence contributions.
- SQLite savepoints prevent optional verification from losing detections.
- JSON evidence already supports future dashboard explanations.
- Adding a module requires an implementation, factory registration,
  configuration, and tests, but no consensus or schema redesign.

Remaining technical debt:

- weights and thresholds are not scientifically calibrated;
- correlated geographic, seasonal, and historical evidence may overstate
  confidence until ablation/calibration data exists;
- evidence records do not yet persist module implementation/configuration
  versions;
- there is no administrative retry job for `verification_unavailable` records;
- the factory is explicit rather than registry-driven, which is acceptable at
  the current module count but should be revisited if integrations proliferate;
- Pi performance and contention behavior remain unmeasured.

## Integration recommendation

**ADDITIONAL DEVELOPMENT REQUIRED**

The code is technically sound and passes full automated validation, but HQ
should not authorize merge under the stated completion criteria until:

1. reviewed local data supports either the existing weights or documented
   replacements; and
2. the enabled Verification V2 profile passes a production Raspberry Pi load
   comparison without harming BirdNET throughput or unattended reliability.

No additional verification feature development is recommended before those two
evidence-gathering activities. If both gates pass without corrective code, the
recommendation can move directly to **READY FOR RC1.1 INTEGRATION**.
