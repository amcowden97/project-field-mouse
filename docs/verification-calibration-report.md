# Verification V2 scientific calibration report

Date: 5 August 2026

Branch/revision: `feature/verification-v2` at `aa128b8`

Decision: **ADDITIONAL FIELD DATA REQUIRED**

## Executive result

Verification V2 remains engineering-complete and its isolated Raspberry Pi
runtime cost is small, but no human-reviewed Field Mouse observations exist in
the available station data. The central question—whether Verification V2
improves detection quality under real-world conditions—therefore cannot yet be
answered with evidence.

No accuracy claim is made. No evidence weight, intercept, decision threshold,
rule threshold, or plugin configuration was changed.

## Dataset inventory

The accessible production-origin station database was queried read-only and
passed `PRAGMA integrity_check`. It is a real observation pool, not a fixture,
but it is not a calibration dataset because it has no ground-truth reviews.

| Candidate-pool characteristic | Count |
| --- | ---: |
| Recordings | 2,820 |
| BirdNET detections | 1,034 |
| Verification decisions | 0 |
| Verification evidence rows | 0 |
| Human reviews | 0 |
| Low confidence, below 0.40 | 454 |
| Middle confidence, 0.40–0.69 | 370 |
| High confidence, at least 0.70 | 210 |
| Taxa with 1–10 detections | 43 |
| Taxa with more than 10 detections | 21 |
| Detections recorded from 05:00 through 08:59 | 42 |
| Recordings with no BirdNET detection | 2,240 |

The most frequent predicted taxa include Black-capped Chickadee (248),
California Scrub-Jay (121), Dark-eyed Junco (116), Downy Woodpecker (54), and
White-breasted Nuthatch (47). These are classifier predictions, not confirmed
species occurrences.

The active RC1 database is under `/var/lib/fieldmouse` and is deliberately not
readable by the operator account. Its dashboard API reported 1,302 detections
during validation, but it exposes no human review records. The accessible
legacy station database likewise contains exactly zero reviews. Neither source
can supply scientific labels.

### Required review protocol

Before export, a qualified reviewer must examine the original WAV segment and
a correctly scaled sonogram, with date/time and habitat context available but
the Verification V2 recommendation initially hidden to limit anchoring.

Each decision must be appended through `detection_reviews` with:

- `verified`, `rejected`, or `corrected_species` state;
- reviewer identity and UTC review time;
- short notes naming audible/visual evidence and uncertainty;
- corrected common/scientific name when applicable;
- confirmation that audio was playable and the complete detection window was
  examined.

The first curated version should include common and low-frequency taxa across
all three confidence bands, confirmed false positives, noisy/difficult audio,
dawn chorus, quiet/background recordings, and multiple dates. Multiple
detections from one WAV must remain in the same split. A second reviewer should
independently audit all rejected/corrected records and a random positive sample.

Detection-triggered review alone cannot measure BirdNET misses. Random quiet
and dawn/background recordings require independent species-presence labeling
before false negatives or end-to-end recall can be reported.

## Evaluation result

The benchmark/export tooling requires review states `verified`,
`corrected_species`, or `rejected` for ground truth. With zero such records:

| Requested observation | Result |
| --- | --- |
| BirdNET accuracy | Not measurable |
| Verification V2 accuracy | Not measurable |
| False positives reduced | Not measurable |
| False negatives introduced | Not measurable |
| Evidence modules consistently helping | Not measurable |
| Evidence modules providing little value | Not measurable |
| Per-species effects | Not measurable |
| Reliability/calibration curve | Not measurable |

Running the verifier over unlabeled recordings would generate predictions, not
validation. Treating those predictions as truth would make the comparison
circular.

## Calibration decisions

The assignment permits weight changes only when reviewed observations support
them. None do, so the complete existing profile is retained:

| Evidence source | Original | New | Decision |
| --- | ---: | ---: | --- |
| BirdNET | 1.00 | 1.00 | Unchanged; no labeled comparison |
| Optional second model | 1.25 | 1.25 | Unchanged and disabled |
| Geographic occurrence | 0.65 | 0.65 | Unchanged; no reviewed rare/common sample |
| Season/time | 0.55 | 0.55 | Unchanged; no reviewed seasonal sample |
| Audio quality | 0.50 | 0.50 | Unchanged; no reviewed noise/false-positive sample |
| Verified station history | 0.45 | 0.45 | Unchanged; no verified history exists |
| Intercept | 0.00 | 0.00 | Unchanged |
| Decision threshold | 0.90 | 0.90 | Unchanged |

`config/calibration/default.json` remains marked `uncalibrated_defaults` with
zero samples. No training-only fit was generated or promoted.

## Raspberry Pi performance

Verification V2 revision `aa128b8` was staged outside the active release at
`/home/amcowden97/verification-v2-validation-aa128b8`. It used the production
Python 3.13 environment and a real station detection from the accessible
database. Recorder, BirdNET, and dashboard remained active throughout. The
active release, service definitions, and active production database were not
modified.

Machine-readable output:
[Pi benchmark](../reports/pi5-verification-20260805.json).

| Measurement | Result |
| --- | ---: |
| Iterations | 1,000 |
| Manager startup | 0.575 ms |
| Mean latency | 2.213 ms |
| p95 latency | 2.231 ms |
| Maximum latency | 8.774 ms |
| Process CPU time | 2.30 seconds |
| Mean verifier process CPU while executing | 99.85% of one core |
| Peak verifier RSS | 40,960,000 bytes (39.1 MiB) |
| Temperature before/after | 56.75°C / 57.85°C |
| Firmware throttling flag | `0x0` before and after |
| Queue depth | 0 before and after |
| BirdNET mean latency | 3,709.95 ms before and after |
| BirdNET timing samples | 1,410 before and after |
| Recorder/BirdNET/dashboard restarts | 0 / 0 / 0 |
| Service PIDs | unchanged |

At the observed mean, serial verification throughput is approximately 452
decisions/second. This is far above the station's recording cadence, and the
short isolated run showed no queue, thermal, or service-reliability regression.
The figure measures the current enabled plugins with the optional second model
disabled; it is not a long unattended soak and does not establish accuracy.

Final station health after validation was `ok`, queue depth was zero,
temperature was 55.4°C, and throttling remained `0x0`. Service RSS at handoff
was approximately 10.4 MiB recorder, 128.9 MiB BirdNET, and 3.4 MiB Gunicorn
master; system available memory was approximately 523 MiB with 583 MiB swap
free.

## Remaining uncertainties and exit criteria

1. Curate and freeze a reviewed manifest with representation across the stated
   confidence, rarity, acoustic-condition, time-of-day, and background strata.
2. Record inter-reviewer agreement and adjudicate disagreements.
3. Use station/time-grouped development and held-out partitions.
4. Compare BirdNET and Verification V2 on the identical held-out records,
   including per-species confusion and coverage.
5. Run evidence-source ablation and reliability analysis; change weights only
   for repeatable held-out gains rather than one species or clip.
6. Add independently sampled negative/background audio before claiming
   false-negative or recall performance.
7. Repeat a longer normal-operation observation after enabling Verification V2
   in an approved pre-production window; the isolated performance result alone
   does not prove unattended reliability over days.

## Conclusion

**ADDITIONAL FIELD DATA REQUIRED**

Pi runtime feasibility is supported. Scientific effectiveness is neither
supported nor disproved because no reviewed observations exist. A merge claim
would be evidence-free and contrary to this milestone's objective.
