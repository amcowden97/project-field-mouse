# AI Verification V2

## Purpose

BirdNET remains the primary detector. Verification V2 answers a different
question: how strongly does all available evidence support the claim that the
species was present, and why?

The verification path is:

```text
BirdNET detection
  -> configurable rule engine
  -> independent verification plugins
  -> weighted log-odds consensus
  -> verification + plugin evidence in SQLite
```

The dashboard is not part of this implementation. Consumers can join
`detections`, `verifications`, and `verification_results` to expose the new
fields without changing existing detection records.

## Design

`DetectionContext` is the immutable input to every plugin. A plugin returns a
`PluginResult` containing:

- `verdict`: support, neutral, or oppose
- `score`: the strength/calibration supplied by that evidence source
- `weight`: the configured trust assigned to that source
- `reason`: a human-readable sentence
- `details`: structured, source-specific diagnostic data

`VerificationManager` only knows the `VerificationPlugin` interface. It applies
the rule engine, calls registered plugins, converts plugin failures to explicit
neutral/unavailable results, and gives all evidence to the consensus engine.

Built-in plugins cover:

- a second classifier adapter
- geographic occurrence
- seasonal and time-of-day plausibility
- station history based only on previously verified observations
- audio quality (silence, clipping, RMS, and estimated SNR)

The history plugin deliberately ignores raw/unverified detections. This prevents
a repeated false positive from teaching the station that the species is common.

## Consensus algorithm

Confidence values are not averaged. BirdNET establishes prior log-odds:

```text
L = birdnet_weight * log(p / (1 - p))
```

Each plugin contributes signed evidence:

```text
L += direction * plugin_weight * abs(log(score / (1 - score)))
```

`direction` is +1 for support, -1 for opposition, and 0 for neutral. The final
score is `sigmoid(L)`. This has useful evidence semantics:

- several independent agreements compound;
- a confident disagreement can outweigh weak supporting context;
- neutral or unavailable sources do not dilute other evidence;
- source weights can be calibrated independently;
- every contribution remains stored and explainable.

The default status bands are verified at 90%, probable at 70%, rejected below
35%, and uncertain otherwise. A rule may reject a low BirdNET result before
expensive plugins run, or accept a very strong BirdNET result directly.

All thresholds and weights live in `config/verification.toml`.

## Region configuration

Washington knowledge is outside the core. `config/regions/bremerton-wa.json` is
the initial station package. Another deployment can select a different JSON
profile without modifying Python.

The bundled occurrence list is intentionally small and conservative. It is a
working configuration example, not a comprehensive range authority. Production
profiles should be generated from a versioned source such as eBird Status and
Trends or checklist-frequency exports, retain source/date metadata, and be
reviewed before automatic penalties are enabled.

## Adding a verifier

1. Subclass `VerificationPlugin`.
2. Give it a stable `name`.
3. Implement `verify(context) -> PluginResult`.
4. Register it in `build_verification_manager`.
5. Add tests for support, opposition, unavailable input, and calibration.

Model-specific dependencies must stay inside their adapter. The second-model
contract additionally exposes `predict`, so Perch, TFLite, ONNX, or a remote
service can be exchanged without altering orchestration or consensus.

## Database

`001_verification_v2.sql` extends existing installations and also supplies the
missing checked-in `detections` definition for fresh databases. Migrations are
recorded in `schema_migrations`.

`verifications` stores the final score, status, rule, explanation, and human
review state. `verification_results` stores every plugin output as both queryable
columns and structured JSON. Re-running verification updates the decision and
replaces its source results while preserving the review status.

## Operational limitations and next steps

- The second-model interface is implemented, but no large model is installed by
  default. This keeps Raspberry Pi installation predictable and avoids silently
  accepting a new model license. The recommended Perch integration work is
  described in `second-verifier-research.md`.
- The audio analyzer detects generic degradation. Robust wind/rain/engine
  labels require a separately trained acoustic-event model.
- Scores and weights need calibration against locally reviewed clips. Track
  precision/recall and reliability curves by species rather than treating the
  defaults as universal.
- Add reviewer identity/notes if multiple people will adjudicate detections.
- Snapshot external occurrence data with provenance instead of doing network
  calls in the real-time pipeline.
