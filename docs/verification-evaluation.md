# Verification evaluation and operations

This milestone turns human decisions into versioned ground truth and provides
one repeatable toolchain for BirdNET, consensus, and future model comparisons.

## Human review

Reviews are append-only records in `detection_reviews`. The latest review is a
convenience view; previous decisions remain available for audit and inter-reviewer
agreement analysis.

States are `pending_review`, `verified`, `rejected`, `corrected_species`, and
`ignored`. Corrections preserve the original and corrected taxonomy, reviewer,
date, notes, and confidence before/after review.

Example:

```shell
python scripts/verification_tools.py review 42 verified \
  --reviewer "A. Reviewer" --notes "Call and spectrogram confirmed"
```

Unusual observations are not automatically suppressed. Geographic rarity, a new
station species, unexpected season/time, model disagreement, and uncertain
consensus add structured flags and a 0–100 review priority. They do not alter
the consensus score.

## Evaluation dataset

Export a reproducible JSON Lines manifest:

```shell
python scripts/verification_tools.py export data/evaluation/2026-07-28
```

Use `--copy-mode copy` or `--copy-mode hardlink` to also organize audio under
`verified/`, `false_positive/`, `needs_review/`, and `unknown/`. Manifest mode
does not duplicate recordings. Every row includes station/date, clip interval,
ground truth, all system predictions, structured verification evidence, and
review provenance.

Treat each export as immutable. Record its Git revision and SHA-256 checksum in
experiment notes. Use station/time-grouped splits so segments from the same
recording cannot leak into both training and testing.

Detection-triggered exports cannot measure species that every detector missed.
Recall and false-negative rate become representative only after adding
independently sampled background recordings and labeling both presence and
absence. The metrics tool reports prediction coverage to make missing system
outputs visible.

## Comparative benchmark

```shell
python scripts/verification_tools.py benchmark \
  data/evaluation/2026-07-28/metadata.jsonl \
  reports/benchmark-2026-07-28.json
```

The report contains precision, recall, false-positive/negative rates, accuracy,
F1, binary counts, multiclass confusion matrices, and prediction coverage for:

- BirdNET alone
- BirdNET with verification
- a future second model

It also recomputes consensus while removing one evidence source at a time and
reports the change in F1. This ablation table measures which validators help on
the reviewed set; a negative contribution is a concrete signal to recalibrate,
improve, or disable that source.

Do not compare models on different record sets. Report macro/per-species metrics
once the dataset is large enough; global accuracy can hide weak rare-species
performance.

## Calibration

```shell
python scripts/verification_tools.py calibrate \
  data/evaluation/2026-07-28/metadata.jsonl \
  config/calibration/station-2026-07-28.json
```

Calibration fits non-negative evidence weights with projected logistic
regression and selects a decision threshold on reviewed examples. The generated
JSON is loadable through `calibration_profile` in `verification.toml`; no source
change is required.

The minimum of ten records is a smoke-test guard, not a scientifically useful
sample. Promote calibration only after using a held-out, class-balanced set.
Archive the previous profile and compare reliability, precision, recall, and
per-species regressions before deployment.

## Occurrence profiles

The builder accepts a normalized CSV with:

```text
scientific_name,common_name,month,observation_count,checklist_count
```

Example:

```shell
python scripts/verification_tools.py build-occurrence input.csv \
  config/regions/bremerton-wa-2026.json \
  --region-id bremerton-wa --region-name "Bremerton, Washington" \
  --source-name "licensed eBird regional summary" --source-version 2026
```

Outputs contain source version, generation time, input checksum, observation
frequency, seasonal months, and a mandatory license-review marker. Frequency
thresholds are explicit in `app/evaluation/occurrence.py`.

eBird raw data and Status and Trends products require accepting separate terms;
raw downloads cannot be redistributed, derived products require attribution and
other obligations, and commercial use needs separate permission. Therefore the
repository provides ingestion tooling but does not redistribute eBird data.
Review the current
[raw-data guidance](https://support.ebird.org/en/support/solutions/articles/48001078113-ebird-data-privacy-and-data-use)
and
[Status and Trends terms](https://science.ebird.org/en/status-and-trends/products-access-terms-of-use)
before generating or publishing a profile.

## Raspberry Pi performance

Run on the actual Pi 5, while the station is otherwise idle and then under its
normal workload:

```shell
python scripts/verification_tools.py profile \
  reports/pi5-verification.json --iterations 100
```

The report measures manager startup, min/mean/max latency, process CPU time,
sampled CPU percentage, peak RSS, and Linux thermal-zone temperature before and
after. Run separate profiles with each plugin disabled, then with Perch enabled,
to attribute bottlenecks.

Acceptance criteria should be fixed before testing. Recommended initial gates:

- p95 verification latency below the recording cadence
- no sustained thermal throttling
- peak memory leaves headroom for recording and dashboard services
- no material recorder dropouts
- measurable held-out precision/F1 gain over BirdNET alone

No Raspberry Pi measurements were fabricated in this milestone. The Windows
development environment cannot substitute for station hardware.

## Audio-quality intelligence

The audio plugin now stores clipping, silence, estimated SNR, spectral flatness,
frequency-band energy, frame variability, and conservative interference
likelihoods for wind, rain-like broadband noise, vehicle-like low-frequency
noise, speech/vocalization, and running-water-like stationary noise.

These are quality heuristics, not environmental classifications. Speech is not
penalized because bird vocalizations can occupy the same band. Validate each
likelihood against reviewed Field Mouse audio before increasing its consensus
weight.
