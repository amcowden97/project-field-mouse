# RC1 Dependency Installation Blocker

## Root cause

The controlled Raspberry Pi installation failed while downloading
`tensorflow==2.21.0`. Pip received 277.1 MB of the 282.2 MB ARM64 wheel and
then timed out:

```text
WARNING: Connection timed out while downloading.
error: incomplete-download
Download failed because not enough bytes were received (277.1 MB/282.2 MB)
note: This is an issue with network connectivity, not pip.
hint: Consider using --resume-retries to enable download resumption.
```

Pip exited 1 after 2,407 seconds. Earlier in the same run, remote connections
were aborted while resolving `optree` and `setuptools`; pip's ordinary retry
logic recovered those requests. The first package that ultimately failed was
TensorFlow.

This is a network timeout, not a missing system library, source-build failure,
compiler failure, Python incompatibility, ARM incompatibility, memory
exhaustion, or storage exhaustion. Pip selected a CPython 3.13 aarch64
manylinux wheel for TensorFlow and compatible wheels for all other binary
packages. No compiler was invoked.

At the start of the run the Pi had 17 GB disk available, 488 MiB available
RAM, and 482 MiB free swap. At failure it had 16 GB disk available, 448 MiB
available RAM, and 589 MiB free swap. Across the complete run the low-water
marks were 189.9 MiB available RAM, 343.2 MiB free swap, and 15.1 GiB free
disk. Isolated temporary data peaked at 678.7 MiB. The complete evidence is
retained on the station under:

```text
/home/amcowden97/pfm-dependency-diagnostic-20260729-2/
```

`install.log`, `summary.txt`, `resources.tsv`, and `exit-code` contain the pip
transcript, before/after resources, ten-second resource samples, and exit code.

## Corrective action

The production installer now:

- gives pip ten ordinary request retries and ten resumable-download retries;
- permits 120 seconds without received data before a request times out;
- writes pip's detailed log outside the candidate release under
  `/var/log/fieldmouse/deployments/`;
- prints the persistent log path and its final 30 lines on failure;
- checks architecture, Python venv support, and at least 2 GiB of installation
  workspace before copying or switching a release;
- removes an incomplete virtual environment during automatic rollback.

These changes affect deployment reliability and diagnostics only. They do not
change the selected packages, application code, database, service behavior, or
production runtime.

## Corrective-action validation

The isolated installation was repeated with the production installer's new
network settings. The run started at 2026-07-29 17:13:20 PDT and completed at
18:35:20 PDT (82 minutes). It encountered repeated connection resets, TLS EOF
errors, DNS failures, and socket timeouts.

The TensorFlow wheel timed out four times. Pip retained the bytes already
received and resumed at 1.6 MB, 59.5 MB, 72.9 MB, and 80.1 MB rather than
restarting the 282.2 MB download. The complete pinned environment then
installed successfully, including `tensorflow==2.21.0`, `birdnet==0.2.16`,
and `gunicorn==23.0.0`.

Post-install validation returned:

```text
No broken requirements found.
gunicorn (version 23.0.0)
TensorFlow 2.21.0
```

Imports of TensorFlow, BirdNET, Flask, psutil, NumPy, and soundfile all
succeeded. This validates the corrective network behavior without invoking the
production deployer or changing production.

## Requirements audit

The production input is a fully pinned runtime closure. Direct dependencies
are imported or executed by Project Field Mouse; transitive dependencies are
needed by those direct packages. Build tooling is retained to make environment
creation deterministic. Development tools are already isolated in
`requirements-dev.txt`.

| Package(s) | Classification | Runtime reason |
| --- | --- | --- |
| birdnet | Required, direct | BirdNET analysis service |
| Flask | Required, direct | Dashboard web application |
| gunicorn | Required, direct | Production dashboard server |
| numpy, soundfile | Required, direct | Audio and verification processing |
| psutil | Required, direct | Runtime resource and metrics collection |
| rich | Required, direct | Operator status display |
| absl-py, astunparse, flatbuffers, gast, google-pasta, grpcio, h5py, keras, libclang, ml_dtypes, namex, opt_einsum, optree, protobuf, six, tensorflow, termcolor, typing_extensions, wrapt | Required, transitive | TensorFlow/Keras runtime closure used by BirdNET |
| kagglehub, kagglesdk, ordered-set, packaging, pandas, pyarrow, python-dateutil, PyYAML, requests, scipy, tqdm | Required, transitive | BirdNET model acquisition, metadata, and numerical runtime |
| certifi, charset-normalizer, idna, urllib3 | Required, transitive | HTTP/TLS closure for requests |
| cffi, pycparser | Required, transitive | Native interface closure for soundfile |
| blinker, click, itsdangerous, Jinja2, MarkupSafe, Werkzeug | Required, transitive | Flask runtime closure |
| markdown-it-py, mdurl, Pygments | Required, transitive | Rich rendering closure |
| setuptools, wheel | Build/environment tooling | Virtual-environment and package installation support |
| black, mypy, pre-commit, pytest, ruff | Development only | Present only in `requirements-dev.txt`; not installed in production |

No package in `requirements-production.txt` is classified as optional for the
deployed service suite. Development dependencies are already separate, so no
requirements split is needed for RC1. A future lock-file workflow may separate
short direct inputs from generated transitive pins, but that is not required
to resolve this incident.

## Recovery validation

The failed controlled installation used isolated temp, cache, and virtual
environment directories. It did not invoke the deployer or switch production.
After exit 1:

- legacy recorder, BirdNET, and dashboard units remained active;
- the SQLite `PRAGMA integrity_check` result remained `ok`;
- post-diagnostic counts were 2,614 recordings and 1,034 detections (the
  recorder remained live during diagnosis);
- no `/opt/project-field-mouse/current` cutover occurred;
- recordings, configuration, station identity, and backups were untouched.

The prior transactional deployment failure likewise ran automatic rollback
before cutover and retained its failed release for diagnosis. The new failure
path preserves those semantics while keeping its pip log outside the candidate
release.

After the successful corrective-action validation, the legacy recorder,
BirdNET, and dashboard services remained enabled and active. Production still
had no `/opt/project-field-mouse/current` link, and SQLite integrity remained
`ok`. The test therefore resolved the dependency blocker without causing a
cutover.
