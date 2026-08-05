# Second verifier model research

Research reviewed 28 July 2026. Project links are included so licensing and
deployment assumptions can be rechecked before enabling a model.

## Recommendation

Use **Perch 2.0 behind `SecondModelAdapter`**, initially as an optional ONNX or
TFLite inference service tested on the Raspberry Pi 5. Keep it disabled until
latency, memory, label mapping, and calibration are measured on Field Mouse
clips.

Perch is the strongest fit because it is genuinely independent of BirdNET,
covers more than 10,000 bird species, publishes model/export tooling, and uses
the permissive Apache-2.0 code license. Its EfficientNet lineage and exported
formats offer a plausible CPU path, although the research repository recommends
a GPU for large workloads and warns that parts of its original TensorFlow stack
are dated. The project now directs practical inference users to Perch-Hoplite.

This is deliberately an adapter integration, not a bundled model. Raspberry Pi
5 throughput and model-artifact licensing must be validated with the exact
released artifact, and its taxonomy must be mapped to BirdNET scientific names.

Primary source:
[Google Research Perch repository](https://github.com/google-research/perch).

## Options considered

| Option | Accuracy/evidence | License and openness | Pi deployment | Maintenance/community | Decision |
|---|---|---|---|---|---|
| Merlin Sound ID | Excellent consumer product with global coverage, but no reproducible public model benchmark/artifact for this use | App is free; the Sound ID model is not released as an integrable open model | Mobile deployment proves efficient inference is possible, but there is no supported model package/API for a Pi service | Strong Cornell product and user community | Reject as an integration target; no open model artifact |
| Perch 2.0 | Strong global embedding/classification research; over 10k bird species and useful transfer behavior | Repository is Apache-2.0; verify the downloaded model card separately | Export tooling includes TFLite; CPU is plausible but a roughly hundreds-of-MB artifact needs benchmarking | Active Google Research code, hundreds of stars, practical tooling moving to Hoplite | Recommended optional second model |
| BirdSet | High-quality multi-task benchmark and dataset collection for realistic passive monitoring; it is not one canonical production classifier | Open research code/data have component-specific terms that must be checked | Training examples use PyTorch Lightning/GPU and are too heavy as the station runtime | Valuable research benchmark; PyPI release history is sparse | Use to evaluate models, not as the verifier itself |
| BirdCLEF submissions | Top competition systems can be accurate on the challenge species/domain | Licensing, weights, preprocessing, and taxonomy vary by submission | Ensembles are commonly GPU-oriented and hard to reproduce on a Pi | Annual competition is active, individual solutions are not stable products | Good experimentation pool, poor maintainable default |
| Custom TensorFlow/PyTorch classifier | Can be optimized for local species and noise; quality depends entirely on labeled station data | Project controls code; training-data/model licenses still apply | Quantized TFLite/ONNX can be excellent on CPU | Full training, calibration, drift, and releases become this project's burden | Future local specialist, not immediate general verifier |
| YAMNet/general audio classifiers | Useful for noise/event detection, not fine-grained bird taxonomy | Common implementations are Apache-2.0 | Lightweight TFLite deployment is practical | Mature ecosystem | Consider for wind/rain/engine quality labels only |

BirdSet describes itself as a benchmark and data pipeline rather than a
ready-to-deploy universal classifier, requires Python 3.10–3.12 in its published
package, and demonstrates training with a GPU:
[BirdSet repository](https://github.com/DBD-research-group/BirdSet) and
[BirdSet on PyPI](https://pypi.org/project/birdset/).

Merlin's public material describes Sound ID as an application feature, not a
downloadable open classifier:
[Cornell Lab Merlin Sound ID](https://merlin.allaboutbirds.org/sound-id/).

BirdCLEF is a research competition with datasets and participant solutions, so
the deployable unit and license must be assessed submission by submission:
[BirdCLEF 2025 competition](https://www.kaggle.com/competitions/birdclef-2025).

## Proposed Perch completion work

1. Select an official Perch 2.0 artifact and record its model-card license,
   checksum, input sample rate/window, and label taxonomy.
2. Export or adopt a supported TFLite/ONNX representation; do not add the
   training stack to the station requirements.
3. Implement `predict` with exact BirdNET clip slicing and scientific-name label
   mapping.
4. Benchmark cold start, steady-state CPU time, peak RSS, and thermals on the
   Raspberry Pi 5. Target processing faster than the recording cadence.
5. Calibrate Perch probabilities and the second-model consensus weight using a
   human-reviewed, class-balanced local set.
6. Measure agreement errors: models trained on overlapping public audio are not
   fully statistically independent, even when their architectures differ.
7. Enable it through configuration only after failure behavior and artifact
   updates are operationally documented.

## Milestone 2 decision

Perch remains optional and disabled. The repository license is Apache-2.0 and
the project points to a current Kaggle model plus Perch-Hoplite for practical
inference, but this session could not establish artifact-specific redistribution
terms or measure Pi 5 performance. Bundling or enabling an unmeasured artifact
would not meet the milestone's evidence standard.

`PerchCommandAdapter` completes the Field Mouse boundary without coupling the
station environment to Perch's research dependencies. A separately pinned
runtime accepts a JSON clip request on standard input and returns species,
confidence, and model version on standard output. Isolation makes startup,
memory, CPU, thermal, failure, and accuracy measurements attributable and lets
the model environment be updated independently.

Before enabling it:

- record the exact artifact URL, license, checksum, labels, and taxonomy;
- implement and test the isolated runtime against that artifact;
- export second-model predictions into the same evaluation manifest;
- compare on the identical held-out set;
- run the Pi profiler with and without the plugin;
- require a measurable precision/F1 gain without unacceptable recall or
  operational regressions.
