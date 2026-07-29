# Continuous learning design

The future learning loop is human-governed:

```text
Detection
  -> explainable verification
  -> priority review queue
  -> append-only human review
  -> immutable evaluation snapshot
  -> benchmark and error analysis
  -> candidate calibration/model
  -> held-out comparison
  -> explicit promotion or rollback
```

Nothing automatically retrains or promotes itself. This avoids silent feedback
loops and protects unusual but genuine observations.

## Promotion process

1. Freeze a versioned dataset with reviewer and provenance metadata.
2. Split by recording and time block, stratifying species and review state.
3. Keep a held-out test set untouched during calibration.
4. Record the current configuration as the baseline.
5. Train/calibrate only on the training partition.
6. Compare baseline and candidate on identical held-out examples.
7. Inspect overall and per-species precision, recall, F1, confusion, calibration,
   and prediction coverage.
8. Manually review regressions, especially rare species and high-priority flags.
9. Promote a versioned configuration only if predefined gates pass.
10. Retain the prior profile for immediate rollback.

## Data-quality safeguards

- Count station history only from reviewed/verified observations.
- Preserve every review revision instead of overwriting labels.
- Track reviewer disagreement and periodically re-audit a sample.
- Never treat `ignored` as confirmed absence.
- Include random background clips to measure missed detections.
- Prevent segments from one recording appearing in multiple dataset splits.
- Keep model outputs and evidence generated before review to avoid label leakage.
- Record model artifact hashes, taxonomy versions, and configuration versions.

## Questions each experiment must answer

- Did precision improve over BirdNET alone at comparable recall?
- Which evidence source changed correct and incorrect decisions?
- Which species dominate remaining errors?
- Are probabilities calibrated, or merely well-ranked?
- Does the candidate meet Pi latency, memory, and thermal gates?
- Are gains stable across seasons and time of day?

The benchmark JSON, calibration JSON, occurrence profile, code commit, and
dataset manifest together form the minimum reproducibility bundle.
